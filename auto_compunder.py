# -*- coding: utf-8 -*-
"""
Created on Mon Aug 19 15:24:21 2024

@author: Dario
"""
import alpaca_trade_api as tradeapi
from datetime import datetime, timedelta, timezone

# Configura le tue credenziali API per il trading reale
API_KEY = ''
SECRET_KEY = ''
BASE_URL = 'https://api.alpaca.markets'  # URL per l'ambiente di trading reale

# Inizializza la connessione API
api = tradeapi.REST(API_KEY, SECRET_KEY, BASE_URL, api_version='v2')

# Funzione per filtrare le attività degli ultimi giorni
def get_recent_activities():
    # Ottieni l'ora attuale con fuso orario UTC (offset-aware)
    today = datetime.now(timezone.utc)
    # Se oggi è lunedì, vai a venerdì scorso
    if today.weekday() == 0:  # 0 corrisponde a lunedì
        yesterday = today - timedelta(days=4)
    else:
        yesterday = today - timedelta(days=1)
        
    print(yesterday)
    # Recupera tutte le attività
    activities = api.get_activities()
    
    recent_activities = []
    for activity in activities:
        
        
        if activity.activity_type == 'DIV':
            
            # Usa 'date' per le attività di tipo DIVNRA e altre
            activity_date = datetime.strptime(activity.date, '%Y-%m-%d')
            # Converti activity_date in un oggetto offset-aware
            activity_date = activity_date.replace(tzinfo=timezone.utc)
            if activity_date > yesterday:
                recent_activities.append(activity)
                print(activity)
                
        elif activity.activity_type == 'DIVNRA':
            
            # Usa 'date' per le attività di tipo DIVNRA e altre
            activity_date = datetime.strptime(activity.date, '%Y-%m-%d')
            # Converti activity_date in un oggetto offset-aware
            activity_date = activity_date.replace(tzinfo=timezone.utc)
            if activity_date > yesterday:
                recent_activities.append(activity)
                print(activity)
    
    return recent_activities

# Funzione per processare i dividendi e reinvestirli
def process_dividends():
    activities = get_recent_activities()

    for activity in activities:
        if activity.activity_type == 'DIV':  # Dividendo ricevuto
            ticker = activity.symbol
            
            dividend_amount = float(activity.net_amount)
            
            # Cerca la tassa associata al dividendo
            tax_amount = 0
            for tax_activity in activities:
                if tax_activity.activity_type == 'DIVNRA' and tax_activity.symbol == ticker:
                    
                    tax_amount = float(tax_activity.net_amount)
                    break

            # Calcola l'importo netto disponibile per l'acquisto
            net_amount = dividend_amount - tax_amount

            # Verifica che l'importo netto sia maggiore di $1 e che ci sia abbastanza buying power
            account = api.get_account()
            buying_power = float(account.buying_power)
            if net_amount > 1 and buying_power >= net_amount:
                try:
                    # Effettua un ordine di acquisto di tipo market
                    api.submit_order(
                        symbol=ticker,
                        qty=None,  # Lascia None per specificare il valore in dollari
                        notional=net_amount,
                        side='buy',
                        type='market',
                        time_in_force='day'
                    )
                    print(f"Acquisto di {ticker} per un valore di {net_amount} $ effettuato con successo.")
                except Exception as e:
                    print(f"Errore durante l'acquisto di {ticker}: {e}")
            else:
                print(f"Non è possibile effettuare l'acquisto per {ticker}. Importo: {net_amount}, Buying Power: {buying_power}")
                
if __name__ == "__main__":
    process_dividends()
