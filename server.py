import os
import logging
from datetime import datetime, timezone
import socketserver
import http.server
import urllib.error
from urllib.request import urlopen, Request

import uuid
import jwt
import redis


REDIS_HOST = os.environ["REDIS_HOST"]
REDIS_PORT = os.environ["REDIS_PORT"]
HTTP_PORT = 9098
SECRET = os.environ["SECRET"]

start_time = datetime.now()
requests_processed = 0


def encode_jwt(username: str, date: datetime):
    nonce = JTINonceGenerator.generate()
    payload = {
        "iat": datetime.now(tz=timezone.utc),
        "jti": nonce,
        "payload": {
            "user": username,
            "date": date.isoformat()
        }
    }
    token = jwt.encode(payload, key=SECRET, algorithm="HS512")
    return token


class JTINonceGenerator:
    redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)

    @classmethod
    def __blacklist(cls, token):
        cls.redis.set(token, 1)

    @classmethod
    def __blacklisted(cls, token) -> bool:
        return cls.redis.get(token) is not None

    @classmethod
    def generate(cls):
        nonce = uuid.uuid4().__str__()
        while cls.__blacklisted(nonce):
            nonce = uuid.uuid4().__str__()
        cls.__blacklist(nonce)
        return nonce


class Proxy(http.server.SimpleHTTPRequestHandler):
    def serve_status_page(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        html = f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport"
          content="width=device-width, user-scalable=no, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="ie=edge">
    <title>Proxy Status</title>
</head>
<body>
    <h2>Time Since Server Start: {(datetime.now() - start_time).seconds} seconds</h2>
    <h2>POST requests processed: {requests_processed}</h2>
</body>
</html>
        """
        self.wfile.write(bytes(html, "utf8"))
        return

    def do_GET(self) -> None:
        if self.path == "/status":
            self.serve_status_page()
        else:
            url = self.path[1:]
            try:
                output = urlopen(url)
            except urllib.error.HTTPError as e:
                self.send_response(e.code)
                self.end_headers()
                self.copyfile(e, self.wfile)
                logging.info("error: http error from url -", url)
            except urllib.error.URLError:
                self.send_response(500)
                self.end_headers()
                logging.info("error: could not open url -", url)
            else:
                self.send_response(200)
                self.end_headers()
                self.copyfile(output, self.wfile)

    def do_POST(self):
        global requests_processed

        url = self.path
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length:
            content = self.rfile.read(content_length)
        else:
            content = None

        headers = {**dict(self.headers.items()), "x-my-jwt": encode_jwt("username", datetime.now())}
        req = Request(url, method="POST", data=content, headers=headers)
        try:
            output = urlopen(req)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
            self.copyfile(e, self.wfile)
            logging.info("error: http error from url -", url)
        except urllib.error.URLError:
            self.send_response(500)
            self.end_headers()
            logging.info("error: could not open url -", url)
        else:
            self.send_response(200)
            self.end_headers()
            self.copyfile(output, self.wfile)
        finally:
            requests_processed += 1


if __name__ == "__main__":
    httpd = None
    try:
        socketserver.TCPServer.allow_reuse_address = True
        httpd = socketserver.TCPServer(("0.0.0.0", HTTP_PORT), Proxy)
        print(f"proxy running at port: {HTTP_PORT}")
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("shutdown proxy server")
    finally:
        if httpd:
            httpd.shutdown()
