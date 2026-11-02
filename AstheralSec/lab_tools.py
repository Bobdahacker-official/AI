"""Fixed, low-impact loopback-only tools. Never executes model-produced commands."""
import argparse
import http.client
import ipaddress
import json
from pathlib import Path
import socket

def authorize(scope, host, ports):
    ip = ipaddress.ip_address(host)
    if not ip.is_loopback or host not in scope.get("targets", []):
        raise ValueError("Only explicitly scoped loopback IP literals are allowed")
    if scope.get("authorization_confirmed") is not True:
        raise ValueError("Explicit local-lab authorization is required")
    if not 1 <= len(ports) <= 8:
        raise ValueError("Specify between one and eight ports")
    for port in ports:
        if type(port) is not int or not 1 <= port <= 65535 or port not in scope.get("ports", []):
            raise ValueError("Port is invalid or outside scope")
    return ip

def connectivity(scope, host, ports):
    ip = authorize(scope, host, ports)
    result = []
    for port in ports:
        family = socket.AF_INET6 if ip.version == 6 else socket.AF_INET
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result.append({"host":host, "port":port, "open":s.connect_ex((host,port)) == 0})
    return result

def headers(scope, host, port):
    authorize(scope, host, [port])
    conn = http.client.HTTPConnection(host, port, timeout=2)
    try:
        conn.request("HEAD", "/")
        response = conn.getresponse()
        return {"status":response.status, "headers":response.getheaders(), "redirects_followed":False}
    finally:
        conn.close()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["ports","headers"])
    p.add_argument("--scope", type=Path, required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--ports", default="8000")
    a = p.parse_args()
    try:
        scope = json.loads(a.scope.read_text())
        ports = [int(v) for v in a.ports.split(",")]
        if a.action == "headers" and len(ports) != 1:
            raise ValueError("HEAD checks accept one port")
        result = connectivity(scope, a.host, ports) if a.action == "ports" else headers(scope,a.host,ports[0])
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, http.client.HTTPException) as e:
        p.exit(2, f"Check failed: {e}\n")

if __name__ == "__main__":
    main()
