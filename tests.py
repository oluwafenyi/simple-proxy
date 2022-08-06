import os

import requests


def test_jwt_gets_added_by_proxy():
    payload = {"hello": "world"}
    response = requests.post("http://postman-echo.com/post", data=payload, proxies={"http": f"http://{os.environ['PROXY_HOST']}:9098"})
    data = response.json()
    headers = data["headers"]
    assert "x-my-jwt" in headers
