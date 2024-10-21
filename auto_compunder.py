# -*- coding: utf-8 -*-
"""
Created on Mon Aug 19 15:24:21 2024

@author: Dario
"""
import alpaca_trade_api as tradeapi
from datetime import datetime, timedelta, timezone
import logging
import os

# Configura le tue credenziali API per il trading reale
API_KEY = ''
SECRET_KEY = ''
BASE_URL = 'https://api.alpaca.markets'  # URL per l'ambiente di trading reale

# Configura il logger
logging.basicConfig(
    filename='dividend_reinvestment.log',
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s:%(message)s'
)

# Inizializza la connessione API
try:
    api = tradeapi.REST(API_KEY, SECRET_KEY, BASE_URL, api_version='v2')
    logging.info("Connessione API inizializzata con successo.")
except Exception as e:
    logging.error(f"Errore durante l'inizializzazione della connessione API: {e}")

# Funzione per filtrare le attivita degli ultimi giorni
def get_recent_activities():
    logging.info("Inizio del recupero delle attivita recenti.")
    # Ottieni l'ora attuale con fuso orario UTC (offset-aware)
    today = datetime.now(timezone.utc)
    # Se oggi e lunedi, vai a venerdi scorso
    if today.weekday() == 0:  # 0 corrisponde a lunedi
        yesterday = today - timedelta(days=3)
    else:
        yesterday = today - timedelta(days=1)
        
    logging.debug(f"Data di riferimento per le attivita recenti: {yesterday}")
    # Recupera tutte le attivita
    try:
        activities = api.get_activities()
        logging.info(f"Recuperate {len(activities)} attivita totali.")
    except Exception as e:
        logging.error(f"Errore durante il recupero delle attivita: {e}")
        return []

    recent_activities = []
    for activity in activities:
        activity_date = None
        if activity.activity_type in ['DIV', 'DIVNRA', 'CSD', 'FEE']:
            # Usa 'date' per le attivita di tipo DIVNRA, DIV, CSD e FEE
            activity_date = datetime.strptime(activity.date, '%Y-%m-%d')
            # Converti activity_date in un oggetto offset-aware
            activity_date = activity_date.replace(tzinfo=timezone.utc)
            if activity_date >= yesterday.replace(hour=0, minute=0, second=0, microsecond=0):
                recent_activities.append(activity)
                logging.debug(f"Aggiunta attivita recente: {activity}")
        else:
            continue  # Ignora altri tipi di attivita

    logging.info(f"Trovate {len(recent_activities)} attivita recenti rilevanti.")
    return recent_activities

# Funzione per processare i dividendi e reinvestirli
def process_dividends():
    logging.info("Inizio del processo di reinvestimento dei dividendi.")
    activities = get_recent_activities()

    # Processa i dividendi
    for activity in activities:
        if activity.activity_type == 'DIV':  # Dividendo ricevuto
            ticker = activity.symbol
            dividend_amount = float(activity.net_amount)
            logging.info(f"Dividendo ricevuto: {dividend_amount} $ per {ticker}.")

            # Cerca la tassa associata al dividendo
            tax_amount = 0
            for tax_activity in activities:
                if tax_activity.activity_type == 'DIVNRA' and tax_activity.symbol == ticker:
                    tax_amount = float(tax_activity.net_amount)
                    logging.info(f"Tassa trovata per {ticker}: {tax_amount} $.")
                    break

            # Calcola l'importo netto disponibile per l'acquisto
            net_amount = round(dividend_amount + tax_amount,2)
            logging.debug(f"Importo netto disponibile per {ticker}: {net_amount} $.")

            # Verifica che l'importo netto sia maggiore di $1 e che ci sia abbastanza buying power
            try:
                account = api.get_account()
                buying_power = float(account.buying_power)
                logging.debug(f"Buying Power disponibile: {buying_power} $.")
            except Exception as e:
                logging.error(f"Errore durante il recupero delle informazioni dell'account: {e}")
                continue

            if net_amount > 1 and buying_power >= net_amount:
                try:
                    # Effettua un ordine di acquisto di tipo market
                    order = api.submit_order(
                        symbol=ticker,
                        qty=None,  # Lascia None per specificare il valore in dollari
                        notional=str(net_amount),
                        side='buy',
                        type='market',
                        time_in_force='day'
                    )
                    logging.info(f"Acquisto di {ticker} per un valore di {net_amount} $ effettuato con successo. ID ordine: {order.id}")
                except Exception as e:
                    logging.error(f"Errore durante l'acquisto di {ticker}: {e}")
            else:
                logging.warning(f"Non e possibile effettuare l'acquisto per {ticker}. Importo: {net_amount}, Buying Power: {buying_power}")
        else:
            continue  # Ignora altre attivita per ora

    # Processa i cash deposit (CSD)
    logging.info("Inizio del processo di reinvestimento dei cash deposit.")
    csd_activities = [activity for activity in activities if activity.activity_type == 'CSD']

    # Ottieni la data di ieri per il confronto
    today = datetime.now(timezone.utc)
    if today.weekday() == 0:  # 0 corrisponde a lunedi
        yesterday = today - timedelta(days=3)
    else:
        yesterday = today - timedelta(days=1)
    yesterday_date = yesterday.date()

    for csd_activity in csd_activities:
        # Verifica se l'attivita e avvenuta ieri
        activity_date = datetime.strptime(csd_activity.date, '%Y-%m-%d').date()
        if activity_date == yesterday_date:
            csd_amount = float(csd_activity.net_amount)
            logging.info(f"Cash deposit di {csd_amount} $ ricevuto il {activity_date}.")

            # Cerca il costo del deposito (FEE) associato
            fee_amount = 0
            for fee_activity in activities:
                if fee_activity.activity_type == 'FEE':
                    fee_activity_date = datetime.strptime(fee_activity.date, '%Y-%m-%d').date()
                    if fee_activity_date == activity_date:
                        fee_amount += float(fee_activity.net_amount)
                        logging.info(f"Costo del deposito (FEE) trovato: {fee_amount} $.")

            # Calcola l'importo netto disponibile per l'acquisto
            net_csd_amount = csd_amount - abs(fee_amount)
            logging.debug(f"Importo netto disponibile dopo aver dedotto il FEE: {net_csd_amount} $.")

            if net_csd_amount <= 0:
                logging.warning(f"L'importo netto dopo aver dedotto il FEE e insufficiente per effettuare acquisti.")
                continue

            # Ottieni le posizioni correnti
            try:
                positions = api.list_positions()
                num_positions = len(positions)
                if num_positions == 0:
                    logging.warning("Nessuna posizione disponibile per allocare il cash deposit.")
                    continue
            except Exception as e:
                logging.error(f"Errore durante il recupero delle posizioni: {e}")
                continue

            # Calcola l'importo da allocare per ogni asset
            amount_per_asset = net_csd_amount / num_positions
            logging.debug(f"Importo per asset: {amount_per_asset} $.")

            # Verifica il buying power disponibile
            try:
                account = api.get_account()
                buying_power = float(account.buying_power)
                logging.debug(f"Buying Power disponibile: {buying_power} $.")
                if buying_power < net_csd_amount:
                    logging.warning(f"Buying Power insufficiente. Richiesto: {net_csd_amount}, Disponibile: {buying_power}")
                    continue
            except Exception as e:
                logging.error(f"Errore durante il recupero delle informazioni dell'account: {e}")
                continue

            # Effettua gli ordini di acquisto per ogni posizione
            for position in positions:
                ticker = position.symbol
                try:
                    order = api.submit_order(
                        symbol=ticker,
                        qty=None,  # Lascia None per specificare il valore in dollari
                        notional=amount_per_asset,
                        side='buy',
                        type='market',
                        time_in_force='day'
                    )
                    logging.info(f"Acquisto di {ticker} per un valore di {amount_per_asset} $ effettuato con successo. ID ordine: {order.id}")
                except Exception as e:
                    logging.error(f"Errore durante l'acquisto di {ticker}: {e}")
        else:
            logging.debug(f"Attivita CSD non corrispondente a ieri: {activity_date}")

if __name__ == "__main__":
    process_dividends()
