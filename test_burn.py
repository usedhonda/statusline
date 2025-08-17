#!/usr/bin/env python3
import json
import subprocess
import sys

def test_statusline():
    data = {'session_id': '54ddbf3e-677e-432b-81a3-73629be68335'}
    proc = subprocess.run(['python3', 'statusline.py'], 
                         input=json.dumps(data), 
                         text=True, 
                         capture_output=True)
    
    print("=== OUTPUT ===")
    print(proc.stdout)
    print("\n=== ERRORS ===")
    if proc.stderr:
        print(proc.stderr)
    else:
        print("No errors")

if __name__ == "__main__":
    test_statusline()