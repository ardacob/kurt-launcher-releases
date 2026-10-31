"""Validated kurt:// invitations and per-data-folder local instance forwarding."""
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

from core import LauncherError
from invites import decode_invite

MAX_LINK = 7000


def invite_link(code):
    decode_invite(code)
    value = 'kurt://join/' + code
    if len(value) > MAX_LINK:
        raise LauncherError('Bu davet bağlantı için çok uzun. Davet kodunu veya mod listesi dosyasını paylaşın.')
    return value


def link_code(value):
    if not isinstance(value, str) or len(value) > MAX_LINK or any(c.isspace() for c in value):
        raise LauncherError('Geçersiz Kurt Launcher davet bağlantısı.')
    try: parsed = urlsplit(value)
    except ValueError: raise LauncherError('Geçersiz davet bağlantısı.') from None
    if parsed.scheme != 'kurt' or parsed.netloc != 'join' or parsed.query or parsed.fragment:
        raise LauncherError('Davet bağlantısı kurt://join/ ile başlamalı.')
    code = parsed.path.removeprefix('/')
    decode_invite(code)
    return code


def argument_link(arguments):
    values = [value for value in arguments[1:] if value.lower().startswith('kurt:')]
    if len(values) > 1: raise LauncherError('Tek bir davet bağlantısı açın.')
    if values: link_code(values[0])
    return values[0] if values else None


def channel(root):
    return 'KurtLauncher-' + hashlib.sha256(str(Path(root).resolve()).casefold().encode()).hexdigest()[:32]


def forward(root, value):
    from PySide6.QtNetwork import QLocalSocket
    link_code(value)
    client=QLocalSocket(); client.connectToServer(channel(root))
    if not client.waitForConnected(1800): return False
    payload=json.dumps(value).encode()+b'\n'
    if client.write(payload)!=len(payload):
        client.abort();return False
    client.flush()
    success=client.bytesToWrite()==0 or client.waitForBytesWritten(1800)
    client.disconnectFromServer()
    return success


def listen(window):
    from PySide6.QtNetwork import QLocalServer
    server=QLocalServer(window)
    server.setSocketOptions(QLocalServer.UserAccessOption)
    name=channel(window.store.root)
    QLocalServer.removeServer(name)
    if not server.listen(name): raise LauncherError('Davet bağlantısı alıcısı açılamadı.')
    def accept():
        while server.hasPendingConnections():
            client=server.nextPendingConnection(); client.setReadBufferSize(16000)
            client.setProperty('payload',b'')
            def read(client=client):
                raw=client.property('payload')+bytes(client.readAll())
                if len(raw)>MAX_LINK+100:
                    client.abort(); return
                if b'\n' not in raw:
                    client.setProperty('payload',raw); return
                try:
                    value=json.loads(raw.split(b'\n',1)[0]); link_code(value)
                    window.receive_invite_link(value)
                except (ValueError,TypeError,LauncherError) as exc:
                    window.report(str(exc))
                client.disconnectFromServer()
            client.readyRead.connect(read)
            client.disconnected.connect(client.deleteLater)
            from PySide6.QtCore import QTimer
            QTimer.singleShot(5000,client,client.abort)
            if client.bytesAvailable(): read()
    server.newConnection.connect(accept)
    window.invite_listener=server


def register_protocol(executable):
    import winreg
    path=Path(executable).resolve()
    if path.name.lower()!='kurtlauncher.exe' or not path.is_file():
        raise LauncherError('Davet bağlantısı için kurulu KurtLauncher.exe gerekli.')
    base=r'Software\Classes\kurt'
    for suffix,values in (('',{'':'URL:Kurt Launcher invitation','URL Protocol':''}),
                           (r'\DefaultIcon',{'':f'"{path}",0'}),
                           (r'\shell\open\command',{'':f'"{path}" "%1"'})):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,base+suffix) as key:
            for name,value in values.items():winreg.SetValueEx(key,name,0,winreg.REG_SZ,value)
