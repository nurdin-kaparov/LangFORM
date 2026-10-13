"""Fetch explicitly supplied public HTTPS sources; never search or follow page links."""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin


def public_address(host):
    addresses = [entry[4][0] for entry in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("URL sources must resolve only to public network addresses.")
    return addresses[0]


class SourceText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if tag in {"p", "br", "div", "h1", "h2", "h3", "li", "tr"} and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.hidden:
            self.hidden -= 1
        if tag in {"p", "div", "li", "tr"} and not self.hidden:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=25, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, 443), timeout=self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def fetch_source_url(url):
    for _ in range(4):
        parsed = urlparse(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.port not in {None, 443} or len(url) > 4000):
            raise ValueError("Supply a public HTTPS source without embedded credentials or custom ports.")
        connection = PinnedHTTPS(parsed.hostname, public_address(parsed.hostname))
        try:
            path = (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")
            connection.request("GET", path, headers={"User-Agent": "LangFORM-SourceReader/1.0"})
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                destination = response.getheader("Location")
                if not destination:
                    raise ValueError("Source redirect has no destination.")
                url = urljoin(url, destination)
                continue
            if response.status != 200:
                raise ValueError(f"Source URL returned HTTP {response.status}.")
            content_type = response.getheader("Content-Type", "").lower()
            if not any(kind in content_type for kind in ["text/", "application/json"]):
                raise ValueError("URL processing supports readable text/HTML/JSON. Grant binary documents as local files.")
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise ValueError("URL source exceeds the two-megabyte retrieval limit.")
            text = body.decode("utf-8", errors="replace")
            if "html" in content_type:
                parser = SourceText()
                parser.feed(text)
                text = "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())
            if not text.strip():
                raise ValueError("The source URL contains no readable text.")
            return text
        finally:
            connection.close()
    raise ValueError("The source URL exceeded the redirect limit.")
