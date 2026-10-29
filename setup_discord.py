"""Configuration de l'écran Discord en ligne de commande (même chose que l'onglet Discord
de config_g19.pyw).

1. https://discord.com/developers/applications → New Application (nom : « G19 Monitor »).
2. OAuth2 → note le Client ID et le Client Secret (Reset Secret).
3. OAuth2 → Redirects → ajoute  http://localhost  → Save.
4. Lance ce script, Discord ouvre une fenêtre « Autoriser » : accepte.
"""
import sys

from g19 import config
from g19.discord import CONFIG_FILE, REDIRECT_URI, RpcError, authorize


def main():
    print(__doc__)
    cfg = config.load(CONFIG_FILE, {}) or {}
    client_id = input(f"Client ID [{cfg.get('client_id', '')}] : ").strip() or cfg.get("client_id")
    secret = input("Client Secret [inchangé si vide] : ").strip() or cfg.get("client_secret")
    if not client_id or not secret:
        print("Client ID et Client Secret sont nécessaires.")
        return 1
    print("Accepte la demande d'autorisation dans Discord…")
    try:
        name = authorize(client_id, secret)
    except RpcError as e:
        print(f"Échec : {e}")
        return 1
    except Exception as e:
        print(f"Échec de l'échange du jeton : {e}\n"
              f"Vérifie le secret et que {REDIRECT_URI} est bien dans OAuth2 → Redirects.")
        return 1
    print(f"OK ({name}), accès enregistré dans {config.DATA_DIR / CONFIG_FILE}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
