import sys, socket, selectors

address = (sys.argv[1], int(sys.argv[2]))

sel = selectors.DefaultSelector()
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(address)
s.setblocking(False)

def send(d):
    data = d.readline()
    s.send(data.encode())

def read(soc):
    data = soc.recv(1024)
    if data:
        print(data.decode())

sel.register(s, selectors.EVENT_READ, read)
sel.register(sys.stdin, selectors.EVENT_READ, send)

while True:
    events = sel.select()
    for key, mask in events:
        key.data(key.fileobj)
