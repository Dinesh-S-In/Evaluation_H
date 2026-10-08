#!/bin/sh
cd "$(dirname "$0")"
cat Project_Task.7z.001 Project_Task.7z.002 Project_Task.7z.003 Project_Task.7z.004 > "Project_Task (2).7z"
echo "Merged into Project_Task (2).7z"
sha256sum "Project_Task (2).7z" 2>/dev/null || shasum -a 256 "Project_Task (2).7z"
echo "Expected: $(cat SHA256.txt)"
