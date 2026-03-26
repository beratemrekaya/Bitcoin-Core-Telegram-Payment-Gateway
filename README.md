# ₿ Bitcoin Core & Telegram Payment Gateway

A completely self-hosted, third-party-free Bitcoin payment gateway that connects directly to your own **Bitcoin Core** node. 

This system generates unique SegWit addresses for your customers, tracks incoming payments using an embedded SQLite database, and sends real-time notifications to your **Telegram** account when a payment is detected in the Mempool (0-conf) and when it is fully confirmed.

## 🌟 Features

* **No Middlemen & Zero Fees:** Connects directly to your own Bitcoin Core node via JSON-RPC.
* **Object-Oriented Architecture:** Modular, clean, and highly extensible Python structure.
* **Lightweight Database:** Uses embedded `SQLite3` for persistent invoice tracking (no separate DB server needed).
* **Real-time Telegram Alerts:** 
  * ⏳ Alerts you instantly when a transaction hits the Mempool (0-confirmations).
  * ✅ Alerts you when the payment is included in a block (1+ confirmations).
* **Extensive Logging:** Full terminal logging for monitoring RPC and API traffic.

## ⚠️ Important Security Notice
Before deploying this on **Mainnet**, please test it thoroughly on **Testnet** or **Regtest**. Ensure that your `bitcoin.conf` binds the RPC server strictly to `127.0.0.1` (localhost) so it is not exposed to the public internet.

## 🛠️ Requirements

* A fully synced Bitcoin Core Node (Mainnet or Testnet)
* Python 3.7+
* Telegram Bot API Token (Obtained via BotFather)

## 📦 Installation

1. Clone the repository to your local machine or server:
   bash
   git clone https://github.com/YOUR_USERNAME/bitcoin-telegram-gateway.git
   cd bitcoin-telegram-gateway

##Install the required Python dependencies:

***code***
Bash
pip install -r requirements.txt

##Configure your Bitcoin Core bitcoin.conf file (Example for Testnet):

***code***
Ini
testnet=1
server=1
rpcuser=your_secure_rpc_username
rpcpassword=your_secure_rpc_password
rpcallowip=127.0.0.1
rpcport=18332

(Do not forget to restart bitcoind after making changes)

***⚙️ Configuration***
Open bitcoin_gateway.py and scroll down to the MAIN EXECUTION BLOCK to enter your credentials:

***code***
Python
RPC_USER = "your_secure_rpc_username"
RPC_PASSWORD = "your_secure_rpc_password"
RPC_PORT = 18332 # Testnet: 18332, Mainnet: 8332

TELEGRAM_BOT_TOKEN = "your_bot_token_from_botfather" 
TELEGRAM_CHAT_ID = "your_personal_or_group_chat_id"

## 🚀 Usage
Once configured, simply run the script:

***code***
Bash
python bitcoin_gateway.py
The system will initialize the database, optionally create a demo invoice, and enter a continuous monitoring loop to watch for payments.
