import os
import pandas as pd
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
import schedule
import time
import logging
from web3 import Web3
import krakenex
from datetime import datetime, timedelta
import ta
from pycoingecko import CoinGeckoAPI
import pytz
import asyncio
import warnings
import signal
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import random

# Load environment variables from .env file
load_dotenv()

# Suppress specific warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pandas")

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Constants
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
SYMBOL = os.getenv('SYMBOL')
STOP_LOSS_THRESHOLD = 0.975  # Set stop loss threshold directly in the code
WEB3_INFURA_URL = os.getenv('WEB3_INFURA_URL')
TRUST_WALLET_ADDRESS = os.getenv('TRUST_WALLET_ADDRESS')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')
UNISWAP_ROUTER_ADDRESS = os.getenv('UNISWAP_ROUTER_ADDRESS')
KRAKEN_API_KEY = os.getenv('KRAKEN_API_KEY')
KRAKEN_API_SECRET = os.getenv('KRAKEN_API_SECRET')
ETH_TOKEN_ADDRESS = os.getenv('ETH_TOKEN_ADDRESS')
COINGECKO_API_KEY = os.getenv('COINGECKO_API_KEY')
EMAIL_ADDRESS = os.getenv('EMAIL_PASSWORD')
EMAIL_PASSWORD = os.getenv('EMAIL_ADDRESS')
RECIPIENT_EMAIL = os.getenv('RECEIPENT_ADDRESS')

# Initialize Web3 instance
try:
    logger.info(f"Connecting to Web3 provider at {WEB3_ALCHEMY_URL}")
    web3 = Web3(Web3.HTTPProvider(WEB3_ALCHEMY_URL))
    if not web3.is_connected():
        logger.error("Failed to connect to the Web3 provider.")
        raise ConnectionError("Failed to connect to the Web3 provider.")
    logger.info("Successfully connected to Web3 provider")
except Exception as e:
    logger.error(f"Error connecting to Web3 provider: {e}")
    raise ConnectionError("Failed to connect to the Web3 provider.")

# Initialize Telegram bot
logger.info("Initializing Telegram Bot")
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Initialize Kraken client
kraken_client = krakenex.API()
kraken_client.key = KRAKEN_API_KEY
kraken_client.secret = KRAKEN_API_SECRET

# Initialize CoinGecko client
coingecko_client = CoinGeckoAPI()

# Uniswap Router ABI
uniswap_router_abi = '''
[
    {
        "constant": false,
        "inputs": [
            {
                "name": "amountOutMin",
                "type": "uint256"
            },
            {
                "name": "path",
                "type": "address[]"
            },
            {
                "name": "to",
                "type": "address"
            },
            {
                "name": "deadline",
                "type": "uint256"
            }
        ],
        "name": "swapExactETHForTokens",
        "outputs": [
            {
                "name": "amounts",
                "type": "uint256[]"
            }
        ],
        "payable": true,
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "constant": false,
        "inputs": [
            {
                "name": "amountIn",
                "type": "uint256"
            },
            {
                "name": "amountOutMin",
                "type": "uint256"
            },
            {
                "name": "path",
                "type": "address[]"
            },
            {
                "name": "to",
                "type": "address"
            },
            {
                "name": "deadline",
                "type": "uint256"
            }
        ],
        "name": "swapExactTokensForETH",
        "outputs": [
            {
                "name": "amounts",
                "type": "uint256[]"
            }
        ],
        "payable": false,
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "constant": false,
        "inputs": [
            {
                "name": "amountIn",
                "type": "uint256"
            },
            {
                "name": "amountOutMin",
                "type": "uint256"
            },
            {
                "name": "path",
                "type": "address[]"
            },
            {
                "name": "to",
                "type": "address"
            },
            {
                "name": "deadline",
                "type": "uint256"
            }
        ],
        "name": "swapExactTokensForTokens",
        "outputs": [
            {
                "name": "amounts",
                "type": "uint256[]"
            }
        ],
        "payable": false,
        "stateMutability":"nonpayable",
        "type":"function"
    },
    {
        "constant": false,
        "inputs": [
            {
                "name": "amountIn",
                "type": "uint256"
            },
            {
                "name": "amountOutMin",
                "type": "uint256"
            },
            {
                "name": "path",
                "type": "address[]"
            },
            {
                "name": "to",
                "type": "address"
            },
            {
                "name": "deadline",
                "type": "uint256"
            }
        ],
        "name": "swapExactETHForTokensSupportingFeeOnTransferTokens",
        "outputs": [
            {
                "name": "amounts",
                "type": "uint256[]"
            }
        ],
        "payable": true,
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "constant": false,
        "inputs": [
            {
                "name": "amountIn",
                "type": "uint256"
            },
            {
                "name": "amountOutMin",
                "type": "uint256"
            },
            {
                "name": "path",
                "type": "address[]"
            },
            {
                "name": "to",
                "type": "address"
            },
            {
                "name": "deadline",
                "type": "uint256"
            }
        ],
        "name": "swapExactTokensForETHSupportingFeeOnTransferTokens",
        "outputs": [
            {
                "name": "amounts",
                "type": "uint256[]"
            }
        ],
        "payable": false,
        "stateMutability": "nonpayable",
        "type": "function"
    }
]
'''

# Initialize Uniswap router contract
uniswap_router = web3.eth.contract(address=UNISWAP_ROUTER_ADDRESS, abi=uniswap_router_abi)

# Global variables
opening_price = None
transactions = []
stop_loss_triggered = False

async def send_telegram_message(message):
    try:
        await bot.send_message(chat_id=CHAT_ID, text=message)
        logger.info(f"Sent Telegram message: {message}")
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")

def send_email(subject, message):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = RECIPIENT_EMAIL
        msg['Subject'] = subject

        msg.attach(MIMEText(message, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(EMAIL_ADDRESS, RECIPIENT_EMAIL, text)
        server.quit()

        logger.info(f"Sent email to {RECIPIENT_EMAIL} with subject: {subject}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")

def get_valid_token_price(symbol):
    price = get_token_price(symbol)
    if price is None:
        raise ValueError(f"Failed to fetch token price for {symbol}")
    return price

def get_token_price(symbol):
    try:
        response = kraken_client.query_public('Ticker', {'pair': symbol})
        if 'result' in response and symbol in response['result']:
            price = float(response['result'][symbol]['c'][0])
            return price
        else:
            logger.error(f"Invalid response from Kraken API: {response}")
            return None
    except Exception as kraken_exception:
        logger.warning(f"Kraken API failed: {kraken_exception}")
        try:
            response = coingecko_client.get_price(ids='ethereum', vs_currencies='usd', x_cg_pro_api_key=COINGECKO_API_KEY)
            price = response['ethereum']['usd']
            logger.info(f"Fetched price from CoinGecko: ${price}")
            return price
        except Exception as coingecko_exception:
            logger.error(f"CoinGecko API failed: {coingecko_exception}")
            return None

def fetch_ohlcv(symbol, interval):
    try:
        response = kraken_client.query_public('OHLC', {'pair': symbol, 'interval': interval})
        if 'result' in response and symbol in response['result']:
            data = response['result'][symbol]
            df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count'])
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['close'] = df['close'].astype(float)
            df['vwap'] = df['vwap'].astype(float)
            df['volume'] = df['volume'].astype(float)
            df['timestamp'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('timestamp', inplace=True)
            return df
        else:
            logger.error(f"Invalid response from Kraken API: {response}")
            return None
    except Exception as e:
        logger.error(f"Failed to fetch OHLCV data: {e}")
        return None

def add_technical_indicators(df):
    try:
        if df is not None and not df.empty:
            df['vwap'] = ta.volume.volume_weighted_average_price(df['high'], df['low'], df['close'], df['volume'])
            df['rsi'] = ta.momentum.RSIIndicator(df['close']).rsi()
            df['macd'] = ta.trend.MACD(df['close']).macd()
            df['bollinger_hband'] = ta.volatility.BollingerBands(df['close']).bollinger_hband()
            df['bollinger_lband'] = ta.volatility.BollingerBands(df['close']).bollinger_lband()
            return df
        else:
            logger.error("Empty DataFrame, cannot add technical indicators.")
            return df
    except Exception as e:
        logger.error(f"Failed to add technical indicators: {e}")
        return df

def log_transaction(transaction_type, amount, price):
    global transactions
    try:
        transactions.append({
            'type': transaction_type,
            'amount': amount,
            'price': price,
            'timestamp': datetime.now()
        })
        logger.info(f"Logged transaction: {transaction_type} {amount} at {price}")
    except Exception as e:
        logger.error(f"Failed to log transaction: {e}")

async def execute_buy_order(token_address, amount_in_eth):
    global opening_price
    eth_balance = get_eth_balance()
    if eth_balance < amount_in_eth:
        await send_telegram_message(f"Not enough ETH to execute buy order. Available: {eth_balance} ETH, Required: {amount_in_eth} ETH.")
        logger.info(f"Waiting for 10 minutes before retrying buy order")
        await asyncio.sleep(600)  # Wait for 10 minutes
        eth_balance = get_eth_balance()  # Re-check ETH balance after waiting
        if eth_balance < amount_in_eth:
            await send_telegram_message(f"Retry failed. Still not enough ETH to execute buy order. Available: {eth_balance} ETH, Required: {amount_in_eth} ETH.")
            return

    amount_in_wei = web3.to_wei(amount_in_eth, 'ether')
    nonce = web3.eth.get_transaction_count(TRUST_WALLET_ADDRESS)
    try:
        opening_price = get_valid_token_price(SYMBOL)
        df = fetch_ohlcv(SYMBOL, interval=1440)
        if df is not None and not df.empty:
            vwap = df['vwap'].iloc[-1]
            current_price = df['close'].iloc[-1]
            if current_price > vwap:
                log_transaction('buy', amount_in_eth, opening_price)

                transaction = uniswap_router.functions.swapExactETHForTokens(
                    0,  # Minimum amount of tokens to receive (slippage protection, set to 0 for demo purposes)
                    [web3.to_checksum_address(TRUST_WALLET_ADDRESS), web3.to_checksum_address(token_address)],  # Path
                    web3.to_checksum_address(TRUST_WALLET_ADDRESS),  # Recipient
                    int(time.time()) + 1000  # Deadline
                ).buildTransaction({
                    'from': TRUST_WALLET_ADDRESS,
                    'value': amount_in_wei,
                    'gas': 2000000,
                    'gasPrice': web3.to_wei('50', 'gwei'),
                    'nonce': nonce
                })

                signed_txn = web3.eth.account.sign_transaction(transaction, private_key=PRIVATE_KEY)
                tx_hash = web3.eth.send_raw_transaction(signed_txn.rawTransaction)
                logger.info(f"Buy order executed: {web3.to_hex(tx_hash)}")
                await send_telegram_message(f"Buy order executed: {web3.to_hex(tx_hash)}")
            else:
                logger.info(f"Current price {current_price} is not greater than VWAP {vwap}. Buy order not executed.")
                await send_telegram_message(f"Current price {current_price} is not greater than VWAP {vwap}. Buy order not executed.")
    except Exception as e:
        logger.error(f"Failed to execute buy order: {e}")

async def execute_sell_order(token_address):
    try:
        if not token_address or not isinstance(token_address, str):
            raise ValueError("Token address must be provided as a non-empty string.")
        
        logger.info(f"Executing sell order with token address: {token_address}")

        # Swap transaction
        df = fetch_ohlcv(SYMBOL, interval=1440)
        if df is not None and not df.empty:
            vwap = df['vwap'].iloc[-1]
            current_price = df['close'].iloc[-1]
            if current_price < vwap:
                swap_txn = uniswap_router.functions.swapExactTokensForETH(
                    web3.to_wei(1, 'ether'),  # Swap a large amount for the test
                    0,  # Minimum amount of ETH to receive (slippage protection, set to 0 for demo purposes)
                    [token_address, web3.to_checksum_address(TRUST_WALLET_ADDRESS)],  # Path
                    web3.to_checksum_address(TRUST_WALLET_ADDRESS),  # Recipient
                    int(time.time()) + 1000  # Deadline
                ).buildTransaction({
                    'from': TRUST_WALLET_ADDRESS,
                    'gas': 2000000,
                    'gasPrice': web3.to_wei('50', 'gwei'),
                    'nonce': web3.eth.get_transaction_count(TRUST_WALLET_ADDRESS)
                })

                signed_swap_txn = web3.eth.account.sign_transaction(swap_txn, private_key=PRIVATE_KEY)
                swap_tx_hash = web3.eth.send_raw_transaction(signed_swap_txn.rawTransaction)
                sold_price = get_valid_token_price(SYMBOL)
                log_transaction('sell', 1, sold_price)  # Log the swap of a large amount for the test
                await send_telegram_message(f"Stop loss triggered! Opening price: ${opening_price}, Sold price: ${sold_price}, Date and time sold: {datetime.now(pytz.timezone('US/Eastern')).strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"Sell order executed: {web3.to_hex(swap_tx_hash)}")
            else:
                logger.info(f"Current price {current_price} is not less than VWAP {vwap}. Sell order not executed.")
                await send_telegram_message(f"Current price {current_price} is not less than VWAP {vwap}. Sell order not executed.")
    except Exception as e:
        logger.error(f"Failed to execute sell order: {e}")

def get_eth_balance():
    try:
        balance = web3.eth.get_balance(TRUST_WALLET_ADDRESS)
        return web3.from_wei(balance, 'ether')
    except Exception as e:
        logger.error(f"Failed to get ETH balance: {e}")
        return 0

async def check_stop_loss(token_address):
    global stop_loss_triggered
    try:
        current_price = get_valid_token_price(SYMBOL)
        if opening_price is not None and current_price < opening_price * STOP_LOSS_THRESHOLD:
            await execute_sell_order(token_address)
            stop_loss_triggered = True
    except Exception as e:
        logger.error(f"Failed to check stop loss: {e}")

def calculate_weekly_report():
    global transactions
    try:
        one_week_ago = datetime.now() - timedelta(days=7)
        weekly_transactions = [t for t in transactions if t['timestamp'] > one_week_ago]
        num_transactions = len(weekly_transactions)
        gains_losses = sum((t['price'] * t['amount']) if t['type'] == 'sell' else -(t['price'] * t['amount']) for t in weekly_transactions)
        return num_transactions, gains_losses
    except Exception as e:
        logger.error(f"Failed to calculate weekly report: {e}")
        return 0, 0

def send_weekly_report():
    num_transactions, gains_losses = calculate_weekly_report()
    report_date = datetime.now().strftime('%Y-%m-%d')
    message = f"Weekly Ethereum Trading Report - {report_date}\nNumber of transactions: {num_transactions}\nGains/Losses: ${gains_losses:.2f}"
    asyncio.run(send_telegram_message(message))
    send_email(f"Weekly Ethereum Trading Report - {report_date}", message)

def handle_response(command):
    responses = ["No Problem", "Let me make this happen", "At Once Sir"]
    return random.choice(responses)

def fetch_1_week_moving_average():
    df = fetch_ohlcv(SYMBOL, interval=1440)  # Fetch daily OHLCV data
    if df is not None and not df.empty:
        df['moving_average'] = df['close'].rolling(window=7).mean()
        return df['moving_average'].iloc[-1]
    else:
        return None

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands = """
    /start - Initializes the bot and confirms it is online
    /buy - Executes a buy order
    /sell - Executes a sell order
    /status - Provides the current status of the bot
    /balance - Shows the current ETH balance and potential gain/loss
    /market - Provides the 1-week moving average of ETH
    /hello - Sends a welcoming message
    """
    response = f"ETH BOT is online! Here are the available commands:\n{commands}"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=response)
    logger.info(response)

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = handle_response("buy")
    await context.bot.send_message(chat_id=update.effective_chat.id, text=response)
    logger.info(response)
    token_address = ETH_TOKEN_ADDRESS
    await execute_buy_order(token_address, get_eth_balance())
    eth_balance = get_eth_balance()
    gas_fee = "0.02 ETH"  # Replace with actual gas fee calculation if needed
    response = f"Buy order executed. Amount: {eth_balance} ETH, Cost: {get_valid_token_price(SYMBOL)} USD, Gas Fee: {gas_fee}"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=response)
    logger.info(response)

async def sell_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = handle_response("sell")
    await context.bot.send_message(chat_id=update.effective_chat.id, text=response)
    logger.info(response)
    token_address = ETH_TOKEN_ADDRESS
    await execute_sell_order(token_address)
    eth_balance = get_eth_balance()
    gas_fee = "0.02 ETH"  # Replace with actual gas fee calculation if needed
    response = f"Sell order executed. Amount: {eth_balance} ETH, Sold at: {get_valid_token_price(SYMBOL)} USD, Gas Fee: {gas_fee}"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=response)
    logger.info(response)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    eth_balance = get_eth_balance()
    current_price = get_valid_token_price(SYMBOL)
    potential_gain_loss = (current_price - opening_price) * eth_balance if opening_price else 0
    response = f"ETH Balance: {eth_balance} ETH\nPotential Gain/Loss: ${potential_gain_loss:.2f}"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=response)
    logger.info(response)

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    eth_balance = get_eth_balance()
    current_price = get_valid_token_price(SYMBOL)
    potential_gain_loss = (current_price - opening_price) * eth_balance if opening_price else 0
    response = f"ETH Balance: {eth_balance} ETH\nPotential Gain/Loss: ${potential_gain_loss:.2f}"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=response)
    logger.info(response)

async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    moving_average = fetch_1_week_moving_average()
    if moving_average:
        response = f"The 1-week moving average of ETH is ${moving_average:.2f}"
    else:
        response = "Failed to fetch the 1-week moving average of ETH."
    await context.bot.send_message(chat_id=update.effective_chat.id, text=response)
    logger.info(response)

async def hello_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    responses = ["Hi", "Greeting good Sir", "Top of the day my good man", "Fancy hearing from you so soon"]
    response = random.choice(responses)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=response)
    logger.info(response)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_type = update.message.chat.type
    text = update.message.text
    print(f'user ({update.message.chat.id}) in {message_type}: "{text}"')

    if message_type == 'group':
        if TELEGRAM_BOT_TOKEN in text:
            new_text = text.replace(TELEGRAM_BOT_TOKEN, '').strip()
            response = handle_response(new_text)
        else:
            return
    else:
        response = handle_response(text)
    
    print('Bot:', response)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=response)

async def handle_error(update: Update, context: ContextTypes.DEFAULT_TYPE, error: Exception):
    logger.error(f"Update {update} caused error {error}")
    logger.info(f"Update {update} caused error {error}")

# Setup Telegram bot application
async def main():
    try:
        application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("buy", buy_command))
        application.add_handler(CommandHandler("sell", sell_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("balance", balance_command))
        application.add_handler(CommandHandler("market", market_command))
        application.add_handler(CommandHandler("hello", hello_command))
        application.add_handler(MessageHandler(filters.TEXT, handle_message))
        application.add_error_handler(handle_error)
        await application.initialize()
        await application.start()
        await send_telegram_message("ETH BOT is online")
        while True:
            # Fetch historical data and check stop loss
            historical_data = fetch_ohlcv(SYMBOL, interval=1440)
            if historical_data is not None:
                # Check stop loss based on the fetched data
                await check_stop_loss(ETH_TOKEN_ADDRESS)

            schedule.run_pending()
            await asyncio.sleep(1)  # Run polling every second

    except Exception as e:
        logger.error(f"Error in main function: {e}")
        await send_telegram_message("ETH BOT is offline")

# Signal handler to send offline message on termination
def signal_handler(sig, frame):
    asyncio.run(send_telegram_message("ETH BOT is offline"))
    logger.info("ETH BOT is offline")
    exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Run the main function with asyncio
if __name__ == '__main__':
    asyncio.run(main())
