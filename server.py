import sys, socket, selectors, hashlib, string, random
import sqlite3, signal, os.path
from datetime import datetime

def connection(sock):
    conn, addr = sock.accept()
    conn.setblocking(False)
    conn.send('Hi. If you want to log in enter 1. If you want to sign up enter 2'.encode())
    sel.register(conn, selectors.EVENT_READ, auth)


def auth(conn):
    data = conn.recv(1024).decode().strip('\n').strip()
    if data:
        sel.unregister(conn)
        if data == '1':
            conn.send('Enter a nickname'.encode())
            sel.register(conn, selectors.EVENT_READ, auth1)
        elif data == '2':
            conn.send('Create a nickname'.encode())
            sel.register(conn, selectors.EVENT_READ, reg)
        else:
            conn.send('If you want to log in enter 1. If you want to sign up enter 2'.encode())
            sel.register(conn, selectors.EVENT_READ, auth)


def auth1(conn):  # nick check
    global check_auth, check_reg
    data = conn.recv(1024).decode().strip('\n').strip()  # nick
    if data:
        sel.unregister(conn)
        if data in clients_db.keys():
            check_auth[conn] = (data, clients_db[data])  # conn: (nick, password)
            conn.send('Enter a password'.encode())
            sel.register(conn, selectors.EVENT_READ, auth2)
        else:
            conn.send("This nickname haven't been registered\nIf you want to log in enter 1. If you want to sign up enter 2".encode())
            sel.register(conn, selectors.EVENT_READ, auth)


def auth2(conn):  # password check
    data = conn.recv(1024).decode().strip('\n').strip()  # password
    if data:
        sel.unregister(conn)
        if hashlib.sha1(data.encode()).hexdigest() == check_auth[conn][1]:
            chat_clients[conn] = check_auth[conn][0]
            clients[conn] = check_auth[conn][0]
            del check_auth[conn]
            conn.send('Logged in'.encode())
            try:
                if nick_room[clients[conn]]:
                    conn.send('\nTo join the room you were in, enter 1. Else 2'.encode())
                    sel.register(conn, selectors.EVENT_READ, join_room)
                else:
                    accept(conn)
            except KeyError:
                accept(conn)
        else:
            conn.send('Incorrect password'.encode())
            conn.close()


def reg(conn):
    data = conn.recv(1024).decode().strip('\n').strip() # nick
    if data:
        sel.unregister(conn)
        if data in clients_db.keys():
            conn.send('This nickname have already been registered. Create a new one'.encode())
            sel.register(conn, selectors.EVENT_READ, reg)
        else:
            conn.send("Nice nick\nNow create a password".encode())
            check_reg[conn] = (data, )
            sel.register(conn, selectors.EVENT_READ, reg1)


def reg1(conn):
    data = conn.recv(1024).decode().strip('\n').strip()  # new password
    if data:
        sel.unregister(conn)
        if len(check_reg[conn]) == 1:
            check_reg[conn] = (check_reg[conn][0], data)  # (nick, password1)
            conn.send('Confirm the password'.encode())
            sel.register(conn, selectors.EVENT_READ, reg1)
        else:
            if check_reg[conn][1] == data:
                conn.send('Registration completed successfully'.encode())
                nick = check_reg[conn][0]
                clients_db[nick] = hashlib.sha1(data.encode()).hexdigest()
                chat_clients[conn] = nick
                clients[conn] = nick
                del check_reg[conn]
                accept(conn)
            else:
                conn.send('Password mismatch\nTry again'.encode())
                sel.register(conn, selectors.EVENT_READ, reg1)


def accept(conn):
    sel.register(conn, selectors.EVENT_READ, read)
    msg = f'{clients[conn]} has entered the chat'
    print(msg)
    for c in chat_clients.keys():
        try:
            c.send(msg.encode())
        except BrokenPipeError:
            sel.unregister(c)
            c.close()
            del chat_clients[c]


def join_room(conn):
    data = conn.recv(1024).decode().strip('\n').strip()  # new password
    if data:
        sel.unregister(conn)
        if data == '1':
            room_name = nick_room[clients[conn]]
            print(f'{clients[conn]} has entered {room_name}')
            msg = f'{clients[conn]} has entered'
            if room_name not in rooms_clients.keys():
                rooms_clients[room_name] = (conn, )
            else:
                rooms_clients[room_name] = rooms_clients[room_name] + (conn, )
            for c in rooms_clients[room_name]:
                if c != conn:
                    try:
                        c.send(msg.encode())
                    except BrokenPipeError:
                        sel.unregister(c)
                        c.close()
                        cl = rooms_clients[client_room[c]]
                        rooms_clients[client_room[c]] = cl[:cl.index(c)] + cl[cl.index(c)+1:]  # a[:a.index(2)] + a[a.index(2)+1:]
                        del client_room[c]
            del chat_clients[conn]
            client_room[conn] = room_name
            sel.register(conn, selectors.EVENT_READ, read_room)
        elif data == '2':
            del nick_room[clients[conn]]
            accept(conn)
        else:
            conn.send('To join the room you were in, enter 1. Else 2'.encode())
            sel.register(conn, selectors.EVENT_READ, join_room)


def read(conn):
    data = conn.recv(1024).decode().strip('\n')
    if data:
        if data[:data.find(' ')] in commands:
            command = data.split()[0]

            if command == '/create':
                if len(data.split()) == 2:
                    room_name = data.split()[1]
                    if room_name not in rooms.keys():
                        password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
                        rooms[room_name] = hashlib.sha1(password.encode()).hexdigest()
                        msg = f'Room was created.\nName: {room_name}\nPassword: {password}'
                        print(msg)
                        conn.send(msg.encode())
                        del chat_clients[conn]
                        rooms_clients[room_name] = (conn, )
                        client_room[conn] = room_name
                        sel.unregister(conn)
                        sel.register(conn, selectors.EVENT_READ, read_room)
                    else:
                        conn.send('A room with the same name have already been registered. Create a new one'.encode())
                else:
                    conn.send('the command must be in the format\n/create <name>'.encode())

            elif command == '/join':
                if len(data.split()) == 3:
                    room_name = data.split()[1]
                    room_password = data.split()[2]
                    if room_name not in rooms.keys() or rooms[room_name] != hashlib.sha1(room_password.encode()).hexdigest():
                        conn.send('Room with this name and password does not exist.\nCheck the correctness of the data'.encode())
                    elif rooms[room_name] == hashlib.sha1(room_password.encode()).hexdigest():
                        print(f'{clients[conn]} has entered {room_name}')
                        msg = f'{clients[conn]} has entered'
                        if room_name not in rooms_clients.keys():
                            rooms_clients[room_name] = (conn, )
                        else:
                            rooms_clients[room_name] = rooms_clients[room_name] + (conn, )
                        for c in rooms_clients[room_name]:
                            if c != conn:
                                try:
                                    c.send(msg.encode())
                                except BrokenPipeError:
                                    sel.unregister(c)
                                    c.close()
                                    cl = rooms_clients[client_room[c]]
                                    rooms_clients[client_room[c]] = cl[:cl.index(c)] + cl[cl.index(c)+1:]  # a[:a.index(2)] + a[a.index(2)+1:]
                                    del client_room[c]
                        del chat_clients[conn]
                        client_room[conn] = room_name
                        sel.unregister(conn)
                        sel.register(conn, selectors.EVENT_READ, read_room)
                else:
                    conn.send('the command must be in the format\n/join <name> <password>'.encode())

        else:
            msg = f"{clients[conn]} ({datetime.now().strftime('%H:%M:%S')}): {data}"
            print(msg)
            cl = chat_clients.copy()
            for c in cl.keys():
                if c != conn:
                    try:
                        c.send(msg.encode())
                    except BrokenPipeError:
                        sel.unregister(c)
                        c.close()
                        del chat_clients[c]


def read_room(conn):
    data = conn.recv(1024).decode().strip('\n')
    if data:
        if data[:data.find(' ')] in commands or data in commands:
            command = data.split()[0]

            if command == '/exit':
                print(data)
                if len(data.split()) == 1:
                    sel.unregister(conn)
                    cl = rooms_clients[client_room[conn]]
                    rooms_clients[client_room[conn]] = cl[:cl.index(conn)] + cl[cl.index(conn)+1:]
                    del client_room[conn]
                    chat_clients[conn] = clients[conn]
                    try:
                        del nick_room[clients[conn]]
                    except KeyError:
                        pass
                    accept(conn)
        
        else:
            msg = f"{client_room[conn]} $ {clients[conn]} ({datetime.now().strftime('%H:%M:%S')}): {data}"
            print(msg)
            for c in rooms_clients[client_room[conn]]:
                if c != conn:
                    try:
                        c.send(msg.encode())
                    except BrokenPipeError:
                        sel.unregister(c)
                        c.close()
                        cl = rooms_clients[client_room[c]]
                        rooms_clients[client_room[c]] = cl[:cl.index(c)] + cl[cl.index(c)+1:]  # a[:a.index(2)] + a[a.index(2)+1:]
                        del client_room[c]


def save(SignalNumber, Frame):
    global clients_db, clients, rooms, rooms_clients, client_room
    conn_sql = sqlite3.connect('clients.db')
    cur = conn_sql.cursor()

    nick_conn = {} # nick: conn
    for key, val in clients.items():
        nick_conn[val] = key

    cl_db = []
    for nick, password in clients_db.items():
        try:
            room_name = client_room[nick_conn[nick]]
        except KeyError:
            try:
                room_name = nick_room[nick]
            except KeyError:
                room_name = None
        cl_db.append((nick, password, room_name))

    #conn = sqlite3.connect('clients.db')
    #cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS clients(
        nick TEXT,
        password TEXT,
        room_name TEXT
    );""")
    cur.execute("""CREATE TABLE IF NOT EXISTS rooms(
        name TEXT,
        password TEXT
    );""")
    cur.execute("""DELETE FROM clients;""")
    cur.execute("""DELETE FROM rooms;""")
    cur.executemany("""INSERT INTO clients VALUES(?, ?, ?);""", cl_db)
    cur.executemany("""INSERT INTO rooms VALUES(?, ?);""", [(room_name, password) for room_name, password in rooms.items()])
    conn_sql.commit()
    sys.exit('\nSave completed successfully')


address = (sys.argv[1], int(sys.argv[2]))
sel = selectors.DefaultSelector()
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind(address)
sock.listen(1000)
sock.setblocking(False)
sel.register(sock, selectors.EVENT_READ, connection)

check_reg = {}  # conn: (nick, password1)
check_auth = {}  # conn: (nick, password)
clients_db = {}  # nick: password
clients = {} # conn: nick
chat_clients = {}  # conn: nick

commands = ('/create', '/join', '/exit')
rooms = {} # name: password
rooms_clients = {} # room: (client1, client2, client3)    ! (client = conn)
client_room = {} # conn: room
nick_room = {} # nick: room

signal.signal(signal.SIGINT, save)

if os.path.isfile('clients.db'):
    conn_sql = sqlite3.connect('clients.db')
    cur = conn_sql.cursor()

    cur.execute("""SELECT * FROM clients;""")
    for nick, password, room_name in cur.fetchall():
        clients_db[nick] = password
        nick_room[nick] = room_name

    cur.execute("""SELECT * FROM rooms;""")
    for room_name, password in cur.fetchall():
        rooms[room_name] = password

while True:
        events = sel.select()
        for key, mask in events:
            callback = key.data
            callback(key.fileobj)
