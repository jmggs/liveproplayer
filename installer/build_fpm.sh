#!/bin/bash
set -e
# Build .deb package for liveproplayer using FPM
# Requirements: fpm, python3, python3-pip, ffmpeg must be installed on the system

PKG_NAME=liveproplayer
PKG_VERSION=0.4.0
BUILD_DIR=liveproplayer-0.4.0

fpm -s dir -t deb \
  -n "$PKG_NAME" \
  -v "$PKG_VERSION" \
  --depends python3 \
  --depends python3-pip \
  --depends ffmpeg \
  --description "LiveProPlayer - player modular para áudio" \
  --maintainer "Seu Nome <email@exemplo.com>" \
  -C "$BUILD_DIR" \
  usr/
