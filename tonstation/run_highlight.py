import argparse
import logging

from tonstation.config import settings
from tonstation.digest_builder import build_and_optionally_send

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description='Run Ton Station weekly highlight once and send/print the digest.'
    )
    parser.add_argument(
        '--print-only',
        action='store_true',
        help='Do not send to Telegram; just print the digest.'
    )
    parser.add_argument(
        '--target',
        type=str,
        default=None,
        help='Override HIGHLIGHT_TARGET_CHAT_ID for this run.'
    )
    args = parser.parse_args()

    send = not args.print_only
    build_and_optionally_send(send=send, target_chat_id=args.target)


if __name__ == '__main__':
    main()
