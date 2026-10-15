"""Deny outbound socket connections in pilot Python processes, including pytest.

This is a cooperative fixture guard, not an adversarial filesystem/network sandbox.
"""

import socket

blocked_attempts = 0


def blocked(*args, **kwargs):
    global blocked_attempts
    blocked_attempts += 1
    raise RuntimeError("Application pilot forbids network connections")


socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.create_connection = blocked
