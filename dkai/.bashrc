#!/bin/bash

export LANG="en_US.UTF-8"
export LC_CTYPE="en_US.UTF-8"

PS1='\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '
PATH="/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin:$HOME/bin:$HOME/.local/bin"

export HISTTIMEFORMAT="%h %d %H:%M:%S "
export HISTSIZE=100000
shopt -s histappend
shopt -s cmdhist

alias ls='ls --color=auto'
