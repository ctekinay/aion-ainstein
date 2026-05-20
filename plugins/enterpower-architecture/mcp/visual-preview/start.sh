#!/bin/bash
cd "$(dirname "$0")"
[ ! -d node_modules ] && npm install --silent
exec node_modules/.bin/tsx src/index.ts
