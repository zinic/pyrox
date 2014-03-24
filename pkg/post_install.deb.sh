#!/bin/sh
# postinst script for pyrox

set -e

case "$1" in
    configure)
        . /usr/share/debconf/confmodule

        if ! (getent group pyrox) > /dev/null 2>&1; then
            addgroup --quiet --system pyrox > /dev/null
        fi

        if ! (getent passwd pyrox) > /dev/null 2>&1; then
            adduser --quiet --system --home /var/lib/pyrox --ingroup pyrox --no-create-home --shell /bin/false pyrox
        fi

        chmod 0755 /etc/init.d/pyrox

        if [ ! -d /var/log/pyrox ]; then
            mkdir /var/log/pyrox
            chown -R pyrox:adm /var/log/pyrox/
            chmod 0755 /var/log/pyrox/
        fi

        if [ ! -d /var/lib/pyrox ]; then
            mkdir /var/lib/pyrox
            chown pyrox:adm -R /var/lib/pyrox/ /etc/pyrox
            chmod -R 0755 /etc/pyrox/
        fi
    ;;

    abort-upgrade|abort-remove|abort-deconfigure)
    ;;

    *)
        echo "postinst called with unknown argument \`$1'" >&2
        exit 1
    ;;
esac

exit 0
