import lib.util
from lib.db import connect


def run():
    conn = connect()
    return lib.util.helper(conn)
