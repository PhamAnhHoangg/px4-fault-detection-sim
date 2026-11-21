"""Stand-in for arduino-cli, used only by the tests."""
import sys
a = sys.argv[1:]
if a[:2] == ["board", "list"]: print('{"detected_ports":[{"port":{"address":"/dev/ttyACM0"},"matching_boards":[{"fqbn":"arduino:avr:uno"}]}]}')
elif a[:1] == ["compile"]:
    if "badboard:x:y" in a: print("Error during build: unknown board"); sys.exit(1)
    print("Sketch uses 924 bytes (2%) of program storage space.")
elif a[:1] == ["upload"]: print("avrdude: 924 bytes of flash written")
else: print("unknown", a); sys.exit(2)
