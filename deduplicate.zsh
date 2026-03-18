#!/bin/zsh
set -eu -o pipefail

tmpfile=$(mktemp)
trap 'rm -f "$tmpfile"' EXIT

# Current directory only; safe for spaces (not newlines in filenames)
find . -maxdepth 1 -type f -print0 | xargs -0 sha256sum > "$tmpfile"

for hash in $(awk '{print $1}' "$tmpfile" | sort | uniq -d); do
  print "Duplicate group (hash=$hash):"

  files=()
  # Extract filenames for this hash without touching internal spaces
  while IFS= read -r fn; do
    files+=("$fn")
  done < <(awk -v h="$hash" '$1==h{ $1=""; sub(/^ +/,""); print }' "$tmpfile")

  # zsh arrays are 1-based
  for ((i=1; i<=${#files}; i++)); do
    print "  [$i] ${files[$i]}"
  done
  print

  typeset -i choice=0
  while true; do
    printf "Enter the number of the file to KEEP: "
    read choice
    if (( choice>=1 && choice<=${#files} )); then break; fi
    print "Invalid choice."
  done

  keep=${files[$choice]}
  print "Keeping: $keep"
  for f in "${files[@]}"; do
    if [[ "$f" != "$keep" ]]; then
      print "Deleting: $f"
      rm -f -- "$f"
    fi
  done
  print
done
