FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# Workaround for stale Yarn apt repo key that can break apt-get update
# during devcontainer feature installation.
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    /usr/share/keyrings/yarnkey.gpg \
    /etc/apt/keyrings/yarn-archive-keyring.gpg
