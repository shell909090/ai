FROM debian:13-slim
COPY packages.txt /srv/packages.txt
COPY ttyd.SHA256SUMS /srv/ttyd.SHA256SUMS
COPY run_agent /usr/bin/run_agent
RUN sed -i 's|deb.debian.org|ftp.cn.debian.org|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install --no-install-recommends -y tmux sudo python3-pip nodejs npm curl ca-certificates locales $(cat /srv/packages.txt) && \
    curl -fsSL -o /usr/bin/ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 && \
    awk '$2=="ttyd.x86_64" { print $1 "  /usr/bin/ttyd" }' /srv/ttyd.SHA256SUMS | sha256sum -c - && \
    rm -f /srv/packages.txt /srv/ttyd.SHA256SUMS && apt-get clean && rm -rf /var/lib/apt/lists/* && \
    chmod +x /usr/bin/ttyd && \
    useradd -m -s /bin/bash -G sudo shell && \
    rm -f /usr/lib/python3.13/EXTERNALLY-MANAGED && \
    npm install -g @google/gemini-cli @anthropic-ai/claude-code @openai/codex opencode-ai && \
    chmod +x /usr/bin/run_agent && \
    sed -i '/^# en_US.UTF-8 UTF-8/s/^# //' /etc/locale.gen && \
    sed -i '/^# zh_CN.UTF-8 UTF-8/s/^# //' /etc/locale.gen && \
    locale-gen && update-locale LANG=en_US.UTF-8
COPY sudoers /etc/sudoers
USER shell
WORKDIR /home/shell
EXPOSE 8484
ENTRYPOINT ["/usr/bin/run_agent"]
