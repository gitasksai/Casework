"""Create or import the HTTPS certificate used by serve.py.

Two ways to get a certificate:

1) Self-signed (quick; each user's PC must trust it once, or browsers will warn):

       python tls_cert.py self-signed --name casework.mycompany.local --ip 10.0.0.25

2) Convert a .pfx/.p12 issued by your company's certificate authority (no browser warnings):

       python tls_cert.py from-pfx C:\\path\\to\\casework.pfx

Both write into ./certs (change with --out):
    cert.pem      certificate (+ any intermediate certificates) -> CASEWORK_SSL_CERT
    key.pem       private key, unencrypted -> CASEWORK_SSL_KEY.  Protect this file.
    casework.crt  (self-signed only) copy of the certificate to install on users' PCs
"""
import argparse
import datetime as dt
import getpass
import ipaddress
import os
import socket
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def _write(path, data):
    with open(path, "wb") as f:
        f.write(data)


def _write_key(path, key):
    _write(path, key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    try:
        os.chmod(path, 0o600)  # no-op on Windows; see docs for icacls
    except OSError:
        pass


def make_self_signed(out_dir, names, ips, days=730):
    """Generate a key and a self-signed server certificate covering `names` and `ips`."""
    os.makedirs(out_dir, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, names[0]),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Casework"),
    ])
    san = [x509.DNSName(n) for n in names] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, key_encipherment=True, content_commitment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False,
            crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM)
    _write(os.path.join(out_dir, "cert.pem"), pem)
    _write(os.path.join(out_dir, "casework.crt"), pem)
    _write_key(os.path.join(out_dir, "key.pem"), key)
    return cert


def convert_pfx(pfx_path, out_dir, password=None):
    """Split a .pfx/.p12 into cert.pem (leaf + intermediates) and key.pem."""
    with open(pfx_path, "rb") as f:
        data = f.read()
    key, cert, extra = pkcs12.load_key_and_certificates(
        data, password.encode() if password else None
    )
    if key is None or cert is None:
        raise ValueError("The .pfx file must contain both a certificate and its private key.")
    os.makedirs(out_dir, exist_ok=True)
    chain = [cert] + [c for c in (extra or []) if c.subject != c.issuer]  # leave out root CAs
    _write(os.path.join(out_dir, "cert.pem"),
           b"".join(c.public_bytes(serialization.Encoding.PEM) for c in chain))
    _write_key(os.path.join(out_dir, "key.pem"), key)
    return cert


def _describe(cert, out_dir):
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        names = [str(v) for v in san.get_values_for_type(x509.DNSName)] + \
                [str(v) for v in san.get_values_for_type(x509.IPAddress)]
    except x509.ExtensionNotFound:
        names = []
    out = os.path.abspath(out_dir)
    print(f"Certificate for: {cert.subject.rfc4514_string()}")
    if names:
        print(f"Valid names:     {', '.join(names)}")
    print(f"Expires:         {cert.not_valid_after_utc:%Y-%m-%d}")
    print()
    print("Set these for the Casework service:")
    print(f"  CASEWORK_SSL_CERT={os.path.join(out, 'cert.pem')}")
    print(f"  CASEWORK_SSL_KEY={os.path.join(out, 'key.pem')}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("self-signed", help="generate a self-signed certificate")
    s.add_argument("--name", action="append", default=[],
                   help="DNS name users will type in the browser (repeatable). "
                        "The server's hostname and 'localhost' are always added.")
    s.add_argument("--ip", action="append", default=[], help="IP address users may browse to (repeatable)")
    s.add_argument("--days", type=int, default=730, help="validity in days (default 730)")
    s.add_argument("--out", default="certs")

    f = sub.add_parser("from-pfx", help="convert a .pfx/.p12 from your certificate authority")
    f.add_argument("pfx")
    f.add_argument("--password", help="PFX password (prompted if omitted)")
    f.add_argument("--out", default="certs")

    args = p.parse_args(argv)
    if args.cmd == "self-signed":
        host = socket.gethostname()
        names = list(dict.fromkeys(args.name + [host, socket.getfqdn(), "localhost"]))
        names = [n for n in names if n]
        ips = list(dict.fromkeys(args.ip + ["127.0.0.1"]))
        cert = make_self_signed(args.out, names, ips, args.days)
        _describe(cert, args.out)
        print()
        print(f"Install {os.path.join(os.path.abspath(args.out), 'casework.crt')} on users' PCs under "
              "'Trusted Root Certification Authorities' to avoid browser warnings.")
    else:
        password = args.password
        if password is None:
            password = getpass.getpass("PFX password (Enter if none): ")
        try:
            cert = convert_pfx(args.pfx, args.out, password or None)
        except ValueError as e:
            sys.exit(f"Could not read {args.pfx}: {e}")
        _describe(cert, args.out)


if __name__ == "__main__":
    main()
