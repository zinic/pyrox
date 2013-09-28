#!/bin/sh
# postrm script for pyrox

set -e

case "$1" in
    purge)
        echo "Purging pyrox..." >&2

        if (getent passwd pyrox) > /dev/null 2>&1; then
            userdel pyrox || true
        fi

        if (getent group pyrox) > /dev/null 2>&1; then
            groupdel pyrox || true
        fi

        [ -e /var/lib/pyrox ] && rm -rf /var/lib/pyrox
        [ -e /var/log/pyrox ] && rm -rf /var/log/pyrox
        [ -e /usr/share/pyrox ] && rm -rf /usr/share/pyrox
        [ -e /etc/pyrox ] && rm -rf /etc/pyrox
    ;;

    upgrade|failed-upgrade|abort-upgrade)
        echo "upgrade ignored"
    ;;

    remove|abort-install|disappear)
        [ -e /usr/share/pyrox ] && rm -rf /usr/share/pyrox
    ;;

    *)
        echo "postrm called with unknown argument \`$1'" >&2
        exit 1
    ;;
esac

exit 0
