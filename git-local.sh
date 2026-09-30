#!/bin/sh
# This workspace reserves .git as read-only. Use .git-local for the local history.
exec git --git-dir=.git-local --work-tree=. "$@"

