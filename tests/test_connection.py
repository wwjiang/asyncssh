# Copyright (c) 2016 by Ron Frederick <ronf@timeheart.net>.
# All rights reserved.
#
# This program and the accompanying materials are made available under
# the terms of the Eclipse Public License v1.0 which accompanies this
# distribution and is available at:
#
#     http://www.eclipse.org/legal/epl-v10.html
#
# Contributors:
#     Ron Frederick - initial implementation, API, and documentation

"""Unit tests for AsyncSSH connection API"""

import asyncio
import os

import asyncssh
from asyncssh.cipher import get_encryption_algs
from asyncssh.compression import get_compression_algs
from asyncssh.kex import get_kex_algs
from asyncssh.mac import get_mac_algs
from asyncssh.public_key import CERT_TYPE_USER

from .server import ServerTestCase
from .util import asynctest, make_certificate


class _InternalErrorClient(asyncssh.SSHClient):
    """Test of internal error exception handler"""

    def connection_made(self, conn):
        """Raise an error when a new connection is opened"""

        # pylint: disable=unused-argument

        raise RuntimeError('Exception handler test')


class _PublicKeyClient(asyncssh.SSHClient):
    """Test public key client auth"""

    def __init__(self, keylist):
        self._keylist = keylist

    def public_key_auth_requested(self):
        """Return a public key to authenticate with"""

        return self._keylist.pop(0) if self._keylist else None


class _PWChangeClient(asyncssh.SSHClient):
    """Test client password change"""

    def password_change_requested(self, prompt, lang):
        """Change the client's password"""

        return 'oldpw', 'pw'


class _TestConnection(ServerTestCase):
    """Unit tests for AsyncSSH connection API"""

    @asyncio.coroutine
    def _connect_publickey(self, keylist):
        """Open a connection to test public key auth"""

        def client_factory():
            """Return an SSHClient to use to do public key auth"""

            return _PublicKeyClient(keylist)

        conn, _ = yield from self.create_connection(client_factory,
                                                    username='ckey',
                                                    client_keys=None)

        return conn

    @asyncio.coroutine
    def _connect_pwchange(self, username, password):
        """Open a connection to test password change"""

        conn, _ = yield from self.create_connection(_PWChangeClient,
                                                    username=username,
                                                    password=password,
                                                    client_keys=None)

        return conn

    @asynctest
    def test_connect_failure(self):
        """Test failure connecting"""

        with self.assertRaises(OSError):
            yield from asyncssh.connect('0.0.0.1')

    @asynctest
    def test_connect_failure_without_agent(self):
        """Test failure connecting with SSH agent disabled"""

        with self.assertRaises(OSError):
            yield from asyncssh.connect('0.0.0.1', agent_path=None)

    @asynctest
    def test_no_auth(self):
        """Test connecting without authentication"""

        with (yield from self.connect(username='guest')) as conn:
            pass

        yield from conn.wait_closed()

    @asynctest
    def test_agent_auth(self):
        """Test connecting with ssh-agent authentication"""

        with (yield from self.connect(username='ckey')) as conn:
            pass

        yield from conn.wait_closed()

    @asynctest
    def test_agent_auth_failure(self):
        """Test failure connecting with ssh-agent authentication"""

        os.environ['HOME'] = 'xxx'

        with self.assertRaises(asyncssh.DisconnectError):
            yield from self.connect(username='ckey', agent_path='xxx')

        os.environ['HOME'] = '.'

    @asynctest
    def test_agent_auth_unset(self):
        """Test connecting with no local keys and no ssh-agent configured"""

        os.environ['HOME'] = 'xxx'
        del os.environ['SSH_AUTH_SOCK']

        with self.assertRaises(asyncssh.DisconnectError):
            yield from self.connect(username='ckey')

        os.environ['HOME'] = '.'
        os.environ['SSH_AUTH_SOCK'] = 'agent'

    @asynctest
    def test_public_key_auth(self):
        """Test connecting with public key authentication"""

        with (yield from self.connect(username='ckey',
                                      client_keys='ckey')) as conn:
            pass

        yield from conn.wait_closed()

    @asynctest
    def test_default_public_key_auth(self):
        """Test connecting with default public key authentication"""

        with (yield from self.connect(username='ckey',
                                      agent_path=None)) as conn:
            pass

        yield from conn.wait_closed()

    @asynctest
    def test_public_key_auth_sshkeypair(self):
        """Test client keys passed in as a list of SSHKeyPairs"""

        agent = yield from asyncssh.connect_agent()
        keylist = yield from agent.get_keys()

        with (yield from self.connect(username='ckey',
                                      client_keys=keylist)) as conn:
            pass

        yield from conn.wait_closed()

        agent.close()

    @asynctest
    def test_public_key_auth_callback(self):
        """Test connecting with public key authentication using callback"""

        with (yield from self._connect_publickey(['ckey'])) as conn:
            pass

        yield from conn.wait_closed()

    @asynctest
    def test_public_key_auth_callback_sshkeypair(self):
        """Test client key passed in as an SSHKeyPair by callback"""

        agent = yield from asyncssh.connect_agent()
        keylist = yield from agent.get_keys()

        with (yield from self._connect_publickey(keylist)) as conn:
            pass

        yield from conn.wait_closed()

        agent.close()

    @asynctest
    def test_public_key_auth_bytes(self):
        """Test client key passed in as bytes"""

        with open('ckey', 'rb') as f:
            ckey = f.read()

        with (yield from self.connect(username='ckey',
                                      client_keys=[ckey])) as conn:
            pass

        yield from conn.wait_closed()

    @asynctest
    def test_public_key_auth_sshkey(self):
        """Test client key passed in as an SSHKey"""

        ckey = asyncssh.read_private_key('ckey')

        with (yield from self.connect(username='ckey',
                                      client_keys=[ckey])) as conn:
            pass

        yield from conn.wait_closed()

    @asynctest
    def test_public_key_auth_cert(self):
        """Test client key with certificate"""

        ckey = asyncssh.read_private_key('ckey')

        cert = make_certificate('ssh-rsa-cert-v01@openssh.com',
                                CERT_TYPE_USER, ckey, ckey, ['ckey'])

        with (yield from self.connect(username='ckey',
                                      client_keys=[(ckey, cert)])) as conn:
            pass

        yield from conn.wait_closed()

    @asynctest
    def test_public_key_auth_missing_cert(self):
        """Test missing client key"""

        with self.assertRaises(OSError):
            yield from self.connect(username='ckey',
                                    client_keys=[('ckey', 'xxx')])

    @asynctest
    def test_public_key_auth_mismatched_cert(self):
        """Test client key with mismatched certificate"""

        skey = asyncssh.read_private_key('skey')

        cert = make_certificate('ssh-rsa-cert-v01@openssh.com',
                                CERT_TYPE_USER, skey, skey, ['skey'])

        with self.assertRaises(ValueError):
            yield from self.connect(username='ckey',
                                    client_keys=[('ckey', cert)])

    @asynctest
    def test_password_auth(self):
        """Test connecting with password authentication"""

        with (yield from self.connect(username='pw', password='pw',
                                      client_keys=None)) as conn:
            pass

        yield from conn.wait_closed()

    @asynctest
    def test_password_auth_failure(self):
        """Test _failure connecting with password authentication"""

        with self.assertRaises(asyncssh.DisconnectError):
            yield from self.connect(username='pw', password='badpw',
                                    client_keys=None)

    @asynctest
    def test_password_change(self):
        """Test password change"""

        with (yield from self._connect_pwchange('pw', 'oldpw')) as conn:
            pass

        yield from conn.wait_closed()

    @asynctest
    def test_password_change_failure(self):
        """Test failure of password change"""

        with self.assertRaises(asyncssh.DisconnectError):
            yield from self._connect_pwchange('nopwchange', 'oldpw')

    @asynctest
    def test_kbdint_auth(self):
        """Test connecting with keyboard-interactive authentication"""

        with (yield from self.connect(username='kbdint', password='kbdint',
                                      client_keys=None)) as conn:
            pass

        yield from conn.wait_closed()

    @asynctest
    def test_kbdint_auth_failure(self):
        """Test failure connecting with keyboard-interactive authentication"""

        with self.assertRaises(asyncssh.DisconnectError):
            yield from self.connect(username='kbdint', password='badpw',
                                    client_keys=None)

    @asynctest
    def test_known_hosts_bytes(self):
        """Test connecting with known hosts passed in as bytes"""

        with open('skey.pub', 'rb') as f:
            skey = f.read()

        with (yield from self.connect(username='guest',
                                      known_hosts=([skey], [], []))) as conn:
            pass

        yield from conn.wait_closed()

    @asynctest
    def test_known_hosts_sshkeys(self):
        """Test connecting with known hosts passed in as SSHKeys"""

        keylist = asyncssh.read_public_key_list('skey.pub')

        with (yield from self.connect(username='guest',
                                      known_hosts=(keylist, [], []))) as conn:
            pass

        yield from conn.wait_closed()

    @asynctest
    def test_known_hosts_failure(self):
        """Test failure to match known hosts"""

        with self.assertRaises(asyncssh.DisconnectError):
            yield from self.connect(known_hosts=([], [], []))

    @asynctest
    def test_kex_algs(self):
        """Test connecting with different key exchange algorithms"""

        for kex in get_kex_algs():
            kex = kex.decode('ascii')
            with self.subTest(kex_alg=kex):
                with (yield from self.connect(username='guest',
                                              kex_algs=[kex])) as conn:
                    pass

                yield from conn.wait_closed()

    @asynctest
    def test_empty_kex_algs(self):
        """Test connecting with an empty list of key exchange algorithms"""

        with self.assertRaises(ValueError):
            yield from self.connect(username='guest', kex_algs=[])

    @asynctest
    def test_invalid_kex_alg(self):
        """Test connecting with invalid key exchange algorithm"""

        with self.assertRaises(ValueError):
            yield from self.connect(username='guest', kex_algs=['xxx'])

    @asynctest
    def test_encryption_algs(self):
        """Test connecting with different encryption algorithms"""

        for enc in get_encryption_algs():
            enc = enc.decode('ascii')
            with self.subTest(encryption_alg=enc):
                with (yield from self.connect(username='guest',
                                              encryption_algs=[enc])) as conn:
                    pass

                yield from conn.wait_closed()

    @asynctest
    def test_empty_encryption_algs(self):
        """Test connecting with an empty list of encryption algorithms"""

        with self.assertRaises(ValueError):
            yield from self.connect(username='guest', encryption_algs=[])

    @asynctest
    def test_invalid_encryption_alg(self):
        """Test connecting with invalid encryption algorithm"""

        with self.assertRaises(ValueError):
            yield from self.connect(username='guest', encryption_algs=['xxx'])

    @asynctest
    def test_mac_algs(self):
        """Test connecting with different MAC algorithms"""

        for mac in get_mac_algs():
            mac = mac.decode('ascii')
            with self.subTest(mac_alg=mac):
                with (yield from self.connect(username='guest',
                                              mac_algs=[mac])) as conn:
                    pass

                yield from conn.wait_closed()

    @asynctest
    def test_empty_mac_algs(self):
        """Test connecting with an empty list of MAC algorithms"""

        with self.assertRaises(ValueError):
            yield from self.connect(username='guest', mac_algs=[])

    @asynctest
    def test_invalid_mac_alg(self):
        """Test connecting with invalid MAC algorithm"""

        with self.assertRaises(ValueError):
            yield from self.connect(username='guest', mac_algs=['xxx'])

    @asynctest
    def test_compression_algs(self):
        """Test connecting with different compression algorithms"""

        for cmp in get_compression_algs():
            cmp = cmp.decode('ascii')
            with self.subTest(cmp_alg=cmp):
                with (yield from self.connect(username='guest',
                                              compression_algs=[cmp])) as conn:
                    pass

                yield from conn.wait_closed()

    @asynctest
    def test_no_compression(self):
        """Test connecting with compression disabled"""

        with (yield from self.connect(username='guest',
                                      compression_algs=None)) as conn:
            pass

        yield from conn.wait_closed()

    @asynctest
    def test_invalid_cmp_alg(self):
        """Test connecting with invalid compression algorithm"""

        with self.assertRaises(ValueError):
            yield from self.connect(username='guest', compression_algs=['xxx'])

    @asynctest
    def test_debug(self):
        """Test sending of debug message"""

        with (yield from self.connect()) as conn:
            conn.send_debug('debug')

        yield from conn.wait_closed()

    @asynctest
    def test_internal_error(self):
        """Test internal error in client callback"""

        with self.assertRaises(RuntimeError):
            yield from self.create_connection(_InternalErrorClient)

    @asynctest
    def test_server_internal_error(self):
        """Test internal error in server callback"""

        with self.assertRaises(asyncssh.DisconnectError):
            yield from self.connect(username='error')
