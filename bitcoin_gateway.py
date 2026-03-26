"""
Bitcoin Core & Telegram Payment Gateway
Requires: pip install -r requirements.txt
Prepared for GitHub Repository deployment.
"""

import requests
import json
import sqlite3
import time
import logging
from datetime import datetime

# Configure logging to output detailed formatting to the terminal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("BTC_Gateway")

class BitcoinRPCError(Exception):
    """Custom exception class for handling Bitcoin Core RPC connection errors."""
    pass

class BitcoinTelegramGateway:
    def __init__(self, rpc_user, rpc_password, rpc_host="127.0.0.1", rpc_port=8332, 
                 telegram_token=None, telegram_chat_id=None, db_name="gateway.db"):
        """
        Initializes the Gateway, setting up RPC parameters and Telegram credentials.
        """
        self.rpc_user = rpc_user
        self.rpc_password = rpc_password
        self.rpc_host = rpc_host
        self.rpc_port = rpc_port
        self.rpc_url = f"http://{self.rpc_user}:{self.rpc_password}@{self.rpc_host}:{self.rpc_port}"
        
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        
        self.db_name = db_name
        self._init_database()

    def _init_database(self):
        """
        Creates the SQLite database and the required tables for persistent invoice tracking.
        Invoice Statuses:
        - 'pending': Waiting for payment
        - 'unconfirmed': Payment detected in mempool (0-conf)
        - 'completed': Payment included in a block (1+ conf)
        """
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT,
                    btc_address TEXT UNIQUE,
                    expected_amount REAL,
                    paid_amount REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            ''')
            conn.commit()
            conn.close()
            logger.info(f"Database initialized successfully. DB Name: {self.db_name}")
        except Exception as e:
            logger.error(f"Critical error while creating the database: {e}")

    def _rpc_call(self, method, params=None):
        """
        Core method to send a secure JSON-RPC POST request to the Bitcoin Core node.
        """
        if params is None:
            params = []
            
        payload = {
            "jsonrpc": "1.0",
            "id": "python_btc_gateway",
            "method": method,
            "params": params
        }
        
        headers = {'content-type': 'text/plain'}
        
        try:
            response = requests.post(
                self.rpc_url, 
                data=json.dumps(payload), 
                headers=headers,
                timeout=15
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("error") is not None:
                raise BitcoinRPCError(f"RPC Error [{method}]: {result['error']}")
                
            return result.get("result")
            
        except requests.exceptions.RequestException as e:
            raise BitcoinRPCError(f"Failed to communicate with Bitcoin Node: {e}")

    def send_telegram_notification(self, message):
        """
        Sends an HTML-formatted notification message to the specified Telegram Chat ID.
        """
        if not self.telegram_token or not self.telegram_chat_id:
            logger.warning("Telegram credentials are missing. Notification skipped.")
            return False

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info("Telegram notification sent successfully.")
                return True
            else:
                logger.error(f"Telegram API rejection: HTTP {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Exception occurred while sending Telegram message: {e}")
            return False

    def create_invoice(self, order_id, expected_amount):
        """
        Requests a new SegWit address from the Bitcoin node, saves the invoice to the DB,
        and triggers a Telegram notification.
        """
        try:
            # Requesting a Bech32 (Native Segwit - bc1/tb1) address for lower fees
            new_address = self._rpc_call("getnewaddress", ["gateway_wallet", "bech32"])
            
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute('''
                INSERT INTO invoices (order_id, btc_address, expected_amount, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (order_id, new_address, expected_amount, 'pending', now, now))
            
            conn.commit()
            conn.close()
            
            logger.info(f"NEW INVOICE -> Address: {new_address} | Amount: {expected_amount} BTC | Order ID: {order_id}")
            
            # Send a notification to Telegram about the newly generated invoice
            msg = (f"🧾 <b>New Invoice Created</b>\n"
                   f"Order ID: <code>{order_id}</code>\n"
                   f"Expected Amount: <b>{expected_amount} BTC</b>\n"
                   f"Deposit Address: <code>{new_address}</code>")
            self.send_telegram_notification(msg)
            
            return new_address
            
        except BitcoinRPCError as e:
            logger.error(f"Failed to generate invoice address (RPC Error): {e}")
            return None
        except Exception as e:
            logger.error(f"Database or unexpected error while creating invoice: {e}")
            return None

    def check_payment_status(self, btc_address, expected_amount, min_confirmations=1):
        """
        Checks the total received amount for a specific address via RPC to determine payment status.
        Returns a tuple: (New_Status, Received_Amount)
        """
        try:
            # '0' param includes unconfirmed transactions currently sitting in the mempool
            unconfirmed_amount = self._rpc_call("getreceivedbyaddress", [btc_address, 0])
            
            # 'min_confirmations' param only includes transactions confirmed in a block
            confirmed_amount = self._rpc_call("getreceivedbyaddress", [btc_address, min_confirmations])
            
            # Status Logic Tree
            if confirmed_amount >= expected_amount:
                return "completed", confirmed_amount
            elif unconfirmed_amount >= expected_amount:
                return "unconfirmed", unconfirmed_amount
            elif unconfirmed_amount > 0 and unconfirmed_amount < expected_amount:
                return "partial", unconfirmed_amount # Detected payment, but less than expected
            else:
                return "pending", 0.0
                
        except BitcoinRPCError as e:
            logger.error(f"RPC error during payment verification for {btc_address}: {e}")
            return "error", 0.0

    def monitor_invoices(self, poll_interval=30, min_confirmations=1):
        """
        The main daemon loop that continuously scans the database for incomplete invoices 
        and verifies their statuses against the Bitcoin network.
        """
        logger.info(f"Payment Monitor Daemon Started. Checking addresses every {poll_interval} seconds...")
        
        while True:
            try:
                conn = sqlite3.connect(self.db_name)
                cursor = conn.cursor()
                
                # Fetch only active invoices to reduce database load
                cursor.execute("SELECT id, order_id, btc_address, expected_amount, status FROM invoices WHERE status != 'completed'")
                active_invoices = cursor.fetchall()
                
                for invoice in active_invoices:
                    inv_id, order_id, address, exp_amount, current_status = invoice
                    
                    # Interrogate the Bitcoin node for the current balance
                    new_status, received_amount = self.check_payment_status(address, exp_amount, min_confirmations)
                    
                    if new_status == "error":
                        continue # Skip this invoice if the RPC call failed, will retry next loop
                        
                    # If a state change is detected, update the database and alert the admin
                    if new_status != current_status and new_status in ["unconfirmed", "completed"]:
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        # Update database record
                        cursor.execute('''
                            UPDATE invoices SET status = ?, paid_amount = ?, updated_at = ? WHERE id = ?
                        ''', (new_status, received_amount, now, inv_id))
                        conn.commit()
                        
                        logger.info(f"Invoice #{inv_id} state changed: {current_status.upper()} -> {new_status.upper()}")
                        
                        # === TELEGRAM NOTIFICATION SCENARIOS ===
                        
                        if new_status == "unconfirmed":
                            # 0-Conf detected. Do not ship digital/physical goods yet to avoid RBF attacks.
                            msg = (f"⏳ <b>Payment Detected (0 Confirmations)</b>\n"
                                   f"Order ID: <code>{order_id}</code>\n"
                                   f"Expected: {exp_amount} BTC\n"
                                   f"Detected: <b>{received_amount} BTC</b>\n"
                                   f"Address: <code>{address}</code>\n"
                                   f"<i>Note: Waiting for network confirmation...</i>")
                            self.send_telegram_notification(msg)
                            
                        elif new_status == "completed":
                            # Transaction mined into a block. Safe to fulfill the order.
                            msg = (f"✅ <b>Payment Confirmed! ({min_confirmations}+ Conf)</b>\n"
                                   f"Order ID: <code>{order_id}</code>\n"
                                   f"Received: <b>{received_amount} BTC</b>\n"
                                   f"Address: <code>{address}</code>\n"
                                   f"🎉 <i>Order is fully paid and completed.</i>")
                            self.send_telegram_notification(msg)
                            
                conn.close()
                
            except Exception as e:
                logger.error(f"Unexpected error in the main monitoring loop: {e}")
                
            # Sleep to prevent overloading the Bitcoin RPC server and CPU
            time.sleep(poll_interval)


# =====================================================================
# MAIN EXECUTION BLOCK (CONFIGURE THIS BEFORE DEPLOYING)
# =====================================================================
if __name__ == "__main__":
    
    # 1. BITCOIN CORE RPC CREDENTIALS
    # Must strictly match the values inside your bitcoin.conf file.
    RPC_USER = "your_rpc_username_here"
    RPC_PASSWORD = "your_rpc_password_here"
    RPC_HOST = "127.0.0.1" 
    RPC_PORT = 18332 # 8332 for Mainnet, 18332 for Testnet, 18443 for Regtest
    
    # 2. TELEGRAM BOT CREDENTIALS
    # Get your bot token from BotFather and find your personal/group Chat ID.
    TELEGRAM_BOT_TOKEN = "123456789:ABCDefghIJKLmnopQRSTuvwxYZ123456" 
    TELEGRAM_CHAT_ID = "-1001234567890" 
    
    # Initialize the Gateway class instance
    gateway = BitcoinTelegramGateway(
        rpc_user=RPC_USER,
        rpc_password=RPC_PASSWORD,
        rpc_host=RPC_HOST,
        rpc_port=RPC_PORT,
        telegram_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID,
        db_name="bitcoin_payments.db"
    )
    
    print("==================================================")
    print("  Initializing Bitcoin & Telegram Payment Gateway ")
    print("==================================================")
    
    # 3. DEMO INVOICE GENERATION (For testing purposes)
    # Uncomment the following block to generate a test invoice upon startup.
    # In a real-world scenario, you would call `create_invoice` from your web backend/API.
    
    # demo_address = gateway.create_invoice(order_id="TEST_ORDER_001", expected_amount=0.005)
    # if demo_address:
    #     print(f"\n[DEMO] Please send exactly 0.005 BTC to: {demo_address}\n")
    
    # 4. START THE MONITORING LOOP
    # This loop polls the database and Node every 15 seconds.
    # We set min_confirmations=1 for basic security (change to 3 or 6 for large amounts).
    try:
        gateway.monitor_invoices(poll_interval=15, min_confirmations=1)
    except KeyboardInterrupt:
        print("\n[!] Ctrl+C detected. Shutting down the gateway safely. Goodbye!")
