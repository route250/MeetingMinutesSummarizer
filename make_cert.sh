#!/bin/bash

DIR=.certs
mkdir -p $DIR
openssl genrsa -out $DIR/server.key 2048

SUBJ="/C=JP" # 国コード
SUBJ="$SUBJ/ST=XX" # 都道府県
SUBJ="$SUBJ/L=XX"  # 市町村
SUBJ="$SUBJ/O=XX"  # 組織名
SUBJ="$SUBJ/OU=XX" # 部署名
SUBJ="$SUBJ/CN=XX" # コモンネーム(FQDNやIP)

openssl req -out $DIR/server.csr -key $DIR/server.key -new -subj "$SUBJ"
cat <<'__EOT__' >$DIR/SAN.txt
subjectAltName = DNS:192.168.1.26
__EOT__
openssl x509 -req -days 3650 -signkey $DIR/server.key -in $DIR/server.csr -out $DIR/server.crt -extfile $DIR/SAN.txt


