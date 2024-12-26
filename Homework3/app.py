import csv
import os

import matplotlib
from flask import Flask, render_template, request, jsonify
import pandas as pd
import datetime
from datetime import timedelta

from matplotlib import pyplot as plt
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import MACD, CCIIndicator
from ta.volatility import BollingerBands

matplotlib.use('Agg')
import io
import base64

app = Flask(__name__)

DATA_FILE = "../Homework1/filtered_stock_data.csv"

# Path to save generated graphs
GRAPH_FOLDER = os.path.join('static', 'graphs')
if not os.path.exists(GRAPH_FOLDER):
    os.makedirs(GRAPH_FOLDER)


# Custom function to handle Macedonian number format (e.g., 2.440,00 -> 2440.00)
def parse_macedonian_price(price_str):
    try:
        # Remove the thousand separator (.)
        price_str = price_str.replace('.', '')
        # Replace decimal separator (,) with dot (.)
        price_str = price_str.replace(',', '.')
        return float(price_str)
    except ValueError:
        return None  # Return None if parsing fails


# Load data initially to fetch issuers
try:
    # Read the CSV and treat the 'Date' column as a string (object)
    df = pd.read_csv(DATA_FILE, dtype={'Date': 'object'})

    # Convert 'Date' column to datetime using the specific format
    df['Date'] = pd.to_datetime(df['Date'], format='%d.%m.%Y')

    # Apply the custom parsing to the 'Average Price' column
    df['Average Price'] = df['Average Price'].apply(parse_macedonian_price)

    # Fetch the list of unique issuers
    issuers = df['Issuer Name'].unique()

except Exception as e:
    df = pd.DataFrame()  # Fallback to an empty DataFrame
    issuers = []  # Default to an empty list if loading fails


@app.route('/')
def index():
    """Render the homepage."""
    return render_template('index.html')


@app.route('/get_todays_data', methods=['GET'])
def get_todays_data():
    """Fetch today's stock data."""
    try:
        # Reload the filtered data
        df = pd.read_csv(DATA_FILE, dtype={'Date': 'object'})

        # Convert 'Date' column to datetime using the specific format
        df['Date'] = pd.to_datetime(df['Date'], format='%d.%m.%Y')

        # Apply the custom price parsing again
        df['Average Price'] = df['Average Price'].apply(parse_macedonian_price)

        # Get today's date
        today = datetime.datetime.now().date()

        # Filter today's data
        todays_data = df[df['Date'].dt.date == today]

        if todays_data.empty:
            last_available_date = df['Date'].max().date()
            todays_data = df[df['Date'].dt.date == last_available_date]

        if todays_data.empty:
            return jsonify([])

        todays_data['Date'] = todays_data['Date'].apply(
            lambda d: d.replace(hour=15, minute=0, second=0).strftime('%Y-%m-%d %H:%M:%S')
        )

        # Return today's data as JSON
        return jsonify(todays_data.to_dict(orient='records'))

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/technicalAnalysis', methods=['GET', 'POST'])
def technical_analysis():
    """Render or analyze the technical analysis page with issuers."""
    if request.method == 'GET':
        # Initialize empty/default variables for GET request
        predicted_prices = {}
        indicators = {}
        graph_base64 = None
        issuer = None

        # Render the technical analysis page without predictions (initial page load)
        return render_template(
            'technicalAnalysis.html',
            issuers=issuers,
            indicators=indicators,
            issuer=issuer,
            graph_base64=graph_base64,
            predicted_prices=predicted_prices
        )

    if request.method == 'POST':
        # Handle the analysis request for a specific issuer
        try:
            issuer = request.form.get('issuer')

            # Check if the issuer is valid
            if issuer not in issuers:
                return jsonify({'error': 'Invalid issuer selected'}), 400

            # Filter data for the selected issuer
            issuer_data = df[df['Issuer Name'] == issuer].sort_values(by='Date')

            if issuer_data.empty:
                return jsonify({'error': 'No data available for the selected issuer'}), 400

            # Ensure data is sorted by date
            issuer_data['Date'] = pd.to_datetime(issuer_data['Date'], errors='coerce')
            issuer_data = issuer_data.set_index('Date')

            # Check if 'Average Price' column exists
            if 'Average Price' not in issuer_data.columns:
                return jsonify({'error': "'Average Price' column is missing in the data"}), 400

            issuer_data['Average Price'] = pd.to_numeric(issuer_data['Average Price'], errors='coerce')
            issuer_data.dropna(subset=['Average Price'], inplace=True)
            issuer_data.sort_index(inplace=True)

            # Calculate technical indicators
            close_prices = issuer_data['Average Price']

            # RSI
            rsi_indicator = RSIIndicator(close=close_prices, window=14)
            rsi = rsi_indicator.rsi()

            # MACD
            macd_indicator = MACD(close=close_prices)
            macd = macd_indicator.macd()
            macd_signal = macd_indicator.macd_signal()
            macd_diff = macd_indicator.macd_diff()

            # Bollinger Bands
            bollinger = BollingerBands(close=close_prices, window=20, window_dev=2)
            bollinger_upper = bollinger.bollinger_hband()
            bollinger_lower = bollinger.bollinger_lband()

            # Simple and Exponential Moving Averages (SMA, EMA)
            sma_20 = close_prices.rolling(window=20).mean()
            sma_50 = close_prices.rolling(window=50).mean()
            ema_20 = close_prices.ewm(span=20, adjust=False).mean()
            ema_50 = close_prices.ewm(span=50, adjust=False).mean()

            # Predict prices based on indicators
            def predict_price(indicator, days_ahead):
                last_value = indicator.iloc[-1]
                return last_value * (1 + (days_ahead * 0.001))

            predicted_prices = {
                '1_day': {
                    'SMA_20': predict_price(sma_20, 1),
                    'SMA_50': predict_price(sma_50, 1),
                    'EMA_20': predict_price(ema_20, 1),
                    'EMA_50': predict_price(ema_50, 1),
                    'RSI': predict_price(rsi, 1),
                    'MACD': predict_price(macd, 1),
                    'Bollinger_Upper': predict_price(bollinger_upper, 1),
                    'Bollinger_Lower': predict_price(bollinger_lower, 1),
                },
                '1_week': {
                    'SMA_20': predict_price(sma_20, 7),
                    'SMA_50': predict_price(sma_50, 7),
                    'EMA_20': predict_price(ema_20, 7),
                    'EMA_50': predict_price(ema_50, 7),
                    'RSI': predict_price(rsi, 7),
                    'MACD': predict_price(macd, 7),
                    'Bollinger_Upper': predict_price(bollinger_upper, 7),
                    'Bollinger_Lower': predict_price(bollinger_lower, 7),
                },
                '1_month': {
                    'SMA_20': predict_price(sma_20, 30),
                    'SMA_50': predict_price(sma_50, 30),
                    'EMA_20': predict_price(ema_20, 30),
                    'EMA_50': predict_price(ema_50, 30),
                    'RSI': predict_price(rsi, 30),
                    'MACD': predict_price(macd, 30),
                    'Bollinger_Upper': predict_price(bollinger_upper, 30),
                    'Bollinger_Lower': predict_price(bollinger_lower, 30),
                }
            }

            # Generate the graph
            plt.figure(figsize=(10, 6))
            plt.plot(close_prices, label='Average Price', color='blue', linestyle='-', linewidth=2)
            plt.plot(sma_20, label='SMA 20', linestyle='--', color='orange')
            plt.plot(sma_50, label='SMA 50', linestyle='--', color='red')
            plt.plot(ema_20, label='EMA 20', linestyle='-', color='green')
            plt.plot(ema_50, label='EMA 50', linestyle='-', color='purple')
            plt.plot(bollinger_upper, label='Bollinger Upper', linestyle=':', color='magenta')
            plt.plot(bollinger_lower, label='Bollinger Lower', linestyle=':', color='cyan')

            plt.title(f'Technical Analysis for {issuer}')
            plt.xlabel('Date')
            plt.ylabel('Price')
            plt.xticks(rotation=45)
            plt.grid(True)
            plt.legend()
            plt.tight_layout()

            # Save the graph as base64
            img_io = io.BytesIO()
            plt.savefig(img_io, format='png')
            img_io.seek(0)
            graph_base64 = base64.b64encode(img_io.getvalue()).decode('utf-8')
            plt.close()

            # Latest values for the indicators
            indicators = {
                'SMA_20': round(sma_20.iloc[-1], 2) if not pd.isna(sma_20.iloc[-1]) else "Недостаток на податоци",
                'SMA_50': round(sma_50.iloc[-1], 2) if not pd.isna(sma_50.iloc[-1]) else "Недостаток на податоци",
                'EMA_20': round(ema_20.iloc[-1], 2) if not pd.isna(ema_20.iloc[-1]) else "Недостаток на податоци",
                'EMA_50': round(ema_50.iloc[-1], 2) if not pd.isna(ema_50.iloc[-1]) else "Недостаток на податоци",
                'RSI': round(rsi.iloc[-1], 2) if not pd.isna(rsi.iloc[-1]) else "Недостаток на податоци",
                'MACD': round(macd.iloc[-1], 2) if not pd.isna(macd.iloc[-1]) else "Недостаток на податоци",
                'Bollinger_Upper': round(bollinger_upper.iloc[-1], 2) if not pd.isna(
                    bollinger_upper.iloc[-1]) else "Недостаток на податоци",
                'Bollinger_Lower': round(bollinger_lower.iloc[-1], 2) if not pd.isna(
                    bollinger_lower.iloc[-1]) else "Недостаток на податоци",
            }

            # Render the template with all the data
            return render_template('technicalAnalysis.html',
                                   indicators=indicators,
                                   issuer=issuer,
                                   issuers=issuers,
                                   graph_base64=graph_base64,
                                   predicted_prices=predicted_prices)

        except Exception as e:
            return jsonify({'error': str(e)}), 500


@app.route('/fundamentalAnalysis', methods=['GET', 'POST'])
def fundamental_analysis():
    issuers = ['ALK', 'CKB', 'GRNT', 'KMB', 'MPT', 'MSTIL', 'MTUR', 'REPL',
               'STB', 'SBT', 'TEL', 'TTK', 'TNB', 'UNI', 'VITA', 'OKTA']

    issuer = None
    description = None

    if request.method == 'POST':
        issuer = request.form['issuer']
        description = get_description_for_issuer(issuer)

    return render_template('fundamentalAnalysis.html', issuers=issuers, selected_issuer=issuer, description=description)

# Helper function to retrieve description for a specific issuer from the CSV file
def get_description_for_issuer(issuer):
    try:
        with open('analysis_results.csv', mode='r', encoding='utf-8') as csvfile:
            csv_reader = csv.DictReader(csvfile)
            for row in csv_reader:
                if row['Issuer Name'] == issuer:
                    return row['Description']
    except Exception as e:
        print(f"Error reading analysis_results.csv: {e}")
    return "Описот не е достапен."

@app.route('/about')
def about():
    return render_template('about_us.html')


if __name__ == '__main__':
    app.run(debug=True)
