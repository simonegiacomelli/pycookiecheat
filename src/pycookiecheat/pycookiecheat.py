"""pycookiecheat.py :: Retrieve and decrypt cookies from Chrome.

See relevant post at http://n8h.me/HufI1w

Use your browser's cookies to make grabbing data from login-protected sites
easier. Intended for use with Python Requests http://python-requests.org

Accepts a URL from which it tries to extract a domain. If you want to force the
domain, just send it the domain you'd like to use instead.

Adapted from my code at http://n8h.me/HufI1w
"""

import pathlib
import sqlite3
import sys
import urllib.error
import urllib.parse
from typing import Iterator, Union

import keyring
from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers.algorithms import AES
from cryptography.hazmat.primitives.ciphers.modes import CBC
from cryptography.hazmat.primitives.hashes import SHA1
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def clean(decrypted: bytes) -> str:
    r"""Strip padding from decrypted value.

    Remove number indicated by padding
    e.g. if last is '\x0e' then ord('\x0e') == 14, so take off 14.

    Args:
        decrypted: decrypted value
    Returns:
        Decrypted stripped of junk padding

    """
    last = decrypted[-1]
    if isinstance(last, int):
        return decrypted[:-last].decode("utf8")
    return decrypted[: -ord(last)].decode("utf8")


def chrome_decrypt(
    encrypted_value: bytes, key: bytes, init_vector: bytes
) -> str:
    """Decrypt Chrome/Chromium's encrypted cookies.

    Args:
        encrypted_value: Encrypted cookie from Chrome/Chromium's cookie file
        key: Key to decrypt encrypted_value
        init_vector: Initialization vector for decrypting encrypted_value
    Returns:
        Decrypted value of encrypted_value

    """
    # Encrypted cookies should be prefixed with 'v10' or 'v11' according to the
    # Chromium code. Strip it off.
    encrypted_value = encrypted_value[3:]

    cipher = Cipher(
        algorithm=AES(key),
        mode=CBC(init_vector),
    )
    decryptor = cipher.decryptor()  # type: ignore
    decrypted = decryptor.update(encrypted_value) + decryptor.finalize()

    return clean(decrypted)


def get_osx_config(browser: str) -> dict:
    """Get settings for getting Chrome/Chromium cookies on OSX.

    Args:
        browser: Either "Chrome" or "Chromium"
    Returns:
        Config dictionary for Chrome/Chromium cookie decryption

    """
    # Verify supported browser, fail early otherwise
    if browser.lower() == "chrome":
        cookie_file = (
            "~/Library/Application Support/Google/Chrome/Default/Cookies"
        )
    elif browser.lower() == "chromium":
        cookie_file = "~/Library/Application Support/Chromium/Default/Cookies"
    else:
        raise ValueError("Browser must be either Chrome or Chromium.")

    config = {
        "my_pass": keyring.get_password(
            "{} Safe Storage".format(browser), browser
        ),
        "iterations": 1003,
        "cookie_file": cookie_file,
    }
    return config


def get_linux_config(browser: str) -> dict:
    """Get the settings for Chrome/Chromium cookies on Linux.

    Args:
        browser: Either "Chrome" or "Chromium"
    Returns:
        Config dictionary for Chrome/Chromium cookie decryption

    """
    # Verify supported browser, fail early otherwise
    if browser.lower() == "chrome":
        cookie_file = "~/.config/google-chrome/Default/Cookies"
    elif browser.lower() == "chromium":
        cookie_file = "~/.config/chromium/Default/Cookies"
    else:
        raise ValueError("Browser must be either Chrome or Chromium.")

    # Set the default linux password
    config = {
        "my_pass": "peanuts",
        "iterations": 1,
        "cookie_file": cookie_file,
    }

    # Try to get pass from Gnome / libsecret if it seems available
    # https://github.com/n8henrie/pycookiecheat/issues/12
    pass_found = False
    try:
        import gi

        gi.require_version("Secret", "1")
        from gi.repository import Secret
    except ImportError:
        pass
    else:
        flags = Secret.ServiceFlags.LOAD_COLLECTIONS
        service = Secret.Service.get_sync(flags)

        gnome_keyring = service.get_collections()
        unlocked_keyrings = service.unlock_sync(gnome_keyring).unlocked

        keyring_name = "{} Safe Storage".format(browser.capitalize())

        for unlocked_keyring in unlocked_keyrings:
            for item in unlocked_keyring.get_items():
                if item.get_label() == keyring_name:
                    item.load_secret_sync()
                    config["my_pass"] = item.get_secret().get_text()
                    pass_found = True
                    break
            else:
                # Inner loop didn't `break`, keep looking
                continue

            # Inner loop did `break`, so `break` outer loop
            break

    # Try to get pass from keyring, which should support KDE / KWallet
    # if dbus-python is installed.
    if not pass_found:
        try:
            my_pass = keyring.get_password(
                "{} Keys".format(browser), "{} Safe Storage".format(browser)
            )
        except RuntimeError:
            pass
        else:
            if my_pass:
                config["my_pass"] = my_pass

    return config


def chrome_cookies(
    url: str,
    cookie_file: str = None,
    browser: str = "Chrome",
    curl_cookie_file: str = None,
    password: Union[bytes, str] = None,
) -> dict:
    """Retrieve cookies from Chrome/Chromium on OSX or Linux.

    Args:
        url: Domain from which to retrieve cookies, starting with http(s)
        cookie_file: Path to alternate file to search for cookies
        browser: Name of the browser's cookies to read ('Chrome' or 'Chromium')
        curl_cookie_file: Path to save the cookie file to be used with cURL
        password: Optional system password
    Returns:
        Dictionary of cookie values for URL

    """

    return dict()


def generate_host_keys(hostname: str) -> Iterator[str]:
    """Yield Chrome/Chromium keys for `hostname`, from least to most specific.

    Given a hostname like foo.example.com, this yields the key sequence:

    example.com
    .example.com
    foo.example.com
    .foo.example.com

    """
    labels = hostname.split(".")
    for i in range(2, len(labels) + 1):
        domain = ".".join(labels[-i:])
        yield domain
        yield "." + domain
