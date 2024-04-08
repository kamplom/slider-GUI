import serial
import re
import time
import threading
from tkinter import *
from PIL import ImageTk, Image
from paho.mqtt import client as pahoMqtt
import serial.tools.list_ports
import asyncio
import websocket


def updatePosText(text):
    text = text + unit
    posText.delete('1.0', END)
    posText.insert(END, text)
    posText.tag_add("center", "1.0", "end")
    posText.tag_configure("center", justify='center')

def showOffsetText(show):
    if show:
        offsetText.place(x=ScreenWidth*0.5,y=ScreenHeight*0.52, width=ScreenWidth, height=115, anchor='center')
    else:
        offsetText.place_forget()


def sendStream(text):
    global focusMain
    global wsapp
    print('sent:' +text)
    if focusMain:
        comPort.write(text.encode())
    elif not focusMain:
        wsapp.send(text.encode())

def plotPos():
    global displayProd
    global displayProy
    global unit
    if guiState == 'distance':
        showOffsetText(False)
        try:
            displayPos = '{:.3f}'.format((abs(pos))/1000+offset)
            updatePosText(displayPos)
            # canvas.itemconfig(posText, text=displayPos+' m')
        except:
            print('not a float')
    elif guiState == 'target':
        showOffsetText(False)
        # canvas.itemconfig(posText, text=userInput+' m')
        updatePosText(userInput)
        # posLabel.config(text=userInput)
        # guiStateLabel.config(text='target')
        # guiStateLabel.pack()
    elif guiState == 'offset':
        showOffsetText(True)
        if not userInput == 'None':
            updatePosText(userInput)
        # guiStateLabel.config(text='offset')
        # guiStateLabel.pack()
    if (not prod == displayProd) or (not proy == displayProy):
        # productoraLabel.config(text=prod)
        displayProd = prod
        # proyectoLabel.config(text=proy)
        displayProy = proy
        

    
    # stateLabel.config(text=grblState)
    root.after(50, plotPos)
    try:
        comPort.write('?'.encode())
    except:
        print("could not wirte ?")
    # print('Sent: ?\n')
    # print(pos)
## Gets serial input from grbl and if it contains position data, updates it.
## Called by Recevie Thread, so called on second thread on each serial polling
def updatePos(picoLine):
    global pos
    if re.match(r'\<([^]]+)\>',picoLine):
        pos = re.split(r',|:',picoLine)[1]
        pos = float(pos)
        if unit == ' ft':
            pos = pos * 3.28084
    return

def ReceiveThread():
    global wsapp
    while comPort:
        try:
            inWaiting = comPort.inWaiting()
            if inWaiting > 2:
                global lines
                global alarmState
                global resetNeed
                global grblState
                global unit

                global pos
                global grblMqttConnected
                global pairConnected
                global homed
                global allowMovement
                lines = comPort.readline().decode('utf-8')
                
                listOfStates = ['Idle', 'Run', 'Hold', 'Jog', 'Alarm', 'Door', 'Check', 'Home', 'Sleep']
                for s in listOfStates:
                    if s in lines:
                        grblState = s
                ##Checks if grbl needs a reset

                if 'Reset to continue' in lines:
                    resetNeed = True

                if re.match(r'\<([^]]+)\>',lines):
                    fields = lines.split('|')
                    for field in fields:
                        if 'Mqtt' in field:
                            grblMqttConnected = re.split(':',field)[1]
                        elif 'AlwMov' in field:
                            allowMovement = re.split(':',field)[1]
                        elif 'Pair' in field:
                            pairConnected = re.split(':',field)[1]
                        elif 'Homed' in field:
                            homed = re.split(':',field)[1]
                        elif 'Pos' in field:
                            aux = re.split(r',|:',field)[1]
                            aux = float(aux)
                            if unit == ' ft':
                                pos = aux * 3.28084
                            elif unit == ' m':
                                pos = aux
                if not re.match(r'\<([^]]+)\>',lines):
                    print(lines)
            else:
                time.sleep(0.01)
        except:
            print("disconnected port")
            connectSerial()
            break;
def requestHoming(event):
    global wsapp
    wsapp.send("?\n".encode())
    # comPort.write('$H\n'.encode())
    sendStream('$HX\n')
    i = 0
    while (not alarmState) and  ('ok' not in lines) and i < 1000:
        time.sleep(0.01)
        i = i + 1
    if i == 1000:
        return 0
    else:
        return 1
    
def requestReset(event):
    global resetNeed
    comPort.write(b'\x18')
    print('Sent: reset\n')
    
def requestJogTemp(event):
    comPort.write('$J=G91 G21 X-449.000 F34800\n'.encode())
    print('Sent: request jog\n')

def requestJog(target, absolute):
    if unit == ' ft':
        target = float(target)
        target = target / 3.28084
        target = '{:.4f}'.format((abs(target)))
    if absolute:
        target = (float(target)-offset)*1000
        jogCommand = '$J=G90 G21 X-'+'{:.3f}'.format(target)+ ' F34800\n'
        print(jogCommand)
        # comPort.write(jogCommand.encode())
        sendStream(jogCommand)
        print('Sent: request jog\n')
    else:
        jogCommand = '$J=G91 G21 X'+target+' F8000'

def introduceOffset(event):
    global guiState
    global userInput
    if guiState == 'distance' or guiState == 'target':
        guiState = 'offset'
    elif guiState == 'offset':
        guiState = 'distance'
    userInput = 'None'

def numCallback(num):
    global userInput
    global guiState
    if guiState == 'distance':
        guiState = 'target'
    if guiState == 'offset' or guiState == 'target':
        print(num)
        updateuserInput (num)

def diffCallback(input):
    global sign
    if guiState == 'distance' and sign == None:
        if input == 'plus':
            sign = '+'
        elif input == 'minus':
            sign = '-'
        else:
            sign = None
    else:
        jogCommand = '$J=G91 G21 X'+sign+input+' F34800\n'
        print(jogCommand)
        comPort.write(jogCommand.encode())
        print('Sent: request jog\n')
        sign = None


def encoderCallback(input):
    jogCommand = '$J=G91 G21 X'+input+'10 F34800\n'
    sendStream(jogCommand)
    # comPort.write(jogCommand.encode())
def enterCallback(event):
    global guiState
    global userInput
    global offset
    if userInput == 'None':
        clearInput(event)
    if guiState == 'target':
        if not userInput == 'None':
            requestJog(userInput, True)
            print('goint there')
            userInput = 'None'
            guiState = 'distance'
    elif guiState == 'offset':
        if not userInput == 'None':
            offset = float(userInput)
            userInput = 'None'
            guiState = 'distance'

def updateuserInput(num):
    global userInput
    if userInput == 'None':
        userInput = num
    elif len(userInput) < 5:
        userInput = userInput + num
        print(userInput)

def clearInput(event):
    global guiState
    global userInput
    print("flush input")
    guiState = 'distance'
    userInput = 'None'

def onMqttMessage(client, userdata, msg):
    global prod
    global proy
    msg = msg.payload.decode()
    if msg == '?':
        send = '3'+displayProd
        mqttClient.publish(topic, '2'+displayProd+';'+displayProy)
    elif msg[0] == '1':
        array = msg[1:].split(';')
        prod = array[0]
        proy = array[1]

def connectSerial():
    global comPort
    while True:
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            if 'CP2102' in p.description:
                port = p.device
        try:
            comPort = serial.Serial('/dev/ttyUSB2',115200)
            # comPort = serial.Serial(port,115200)
        except:
            time.sleep(1)
        if comPort:
            print("calling receiveThread")
            ReceiveThread()

reply_timeout = 10
ping_timeout = 5
sleep_time = 5
url = 'ws://192.168.1.91:80'

def on_open(ws):
    print('open ws success')
    wsapp.send("?\n".encode())

def on_message(ws, message):
    print('message ws:')
    print(message.decode())

def create_ws():
    global wsapp
    while True:
        print('trying')
        try:
            websocket.enableTrace(False)
            wsapp = websocket.WebSocketApp(url,
                                        on_message = on_message)
            wsapp.on_open = on_open
            wsapp.on_message = on_message
            print('running forever')
            wsapp.run_forever(skip_utf8_validation=True,ping_interval=10,ping_timeout=8)
        except Exception as e:
            # gc.collect()
            print("Websocket connection Error  : {0}".format(e))                    
        print("Reconnecting websocket  after 5 sec")
        time.sleep(5)

def unitSwitch(event):
    global unit
    global offset
    if unit == ' m':
        unit = ' ft'
        offset = offset * 3.28084
    else:
        unit = ' m'
        offset = offset / 3.28084

def focusSwitch(event):
    global focusMain
    if focusMain:
        focusMain = False
    elif not focusMain:
        focusMain = True
    else:
        focusMain = True

## Config params
ScreenWidth = 2560
ScreenHeight = 1600

## Initialize pos and lines. It is being updated from the other thread,
## Careful with multithread modification
pos = 0.0
lines = ''
alarmState = 0
resetNeed = False
grblState = ''
guiState = 'distance'
offset = 0
userInput = 'None'
comPort = ''
unit = ' m'
sign = None
wsapp = None
focusMain = True

#MQTT settings
broker = 'broker.emqx.io'
port= 1883
topic = "zigzag/mqtt"
client_id = f'zigzagslider1'
prod = ''
proy = ''
displayProd = ''
displayProy = ''


mqttClient = pahoMqtt.Client(client_id)
mqttClient.connect(broker, port)
mqttClient.loop_start()
mqttClient.subscribe(topic)
mqttClient.on_message = onMqttMessage

root = Tk()
root.geometry(str(ScreenWidth)+'x'+str(ScreenHeight))
root.attributes("-fullscreen", True)  # substitute `Tk` for whatever your `Tk()` object is called

canvas = Canvas(root, bg="white", width=ScreenWidth, height=ScreenHeight)
canvas.place(x=0,y=0)

canvas.create_rectangle(0, 0, ScreenWidth, 500, fill="#f6a0a0", outline='')

# posText = canvas.create_text(ScreenWidth/2, 1080*0.65, text='4562.256', anchor='center', font=('Carlito', 225, 'bold'))

posText = Text(root, borderwidth=0, highlightthickness=1, font=('Carlito', 250, 'bold'))
posText.insert(END, "125.265")

posText.place(x=ScreenWidth*0.5,y=ScreenHeight*0.68, width=ScreenWidth, height=370, anchor='center')

offsetText = Text(root, borderwidth=0, highlightthickness=1, font=('Carlito', 50, 'bold'))
offsetText.insert(END, 'Offset: Introduce offset and press enter')

offsetText.tag_add("center", "1.0", "end")
offsetText.tag_configure("center", justify='center')


# prodProyText = canvas.create_text(ScreenWidth/2, ScreenHeight*0.20, text='GARAGE - "Lambo"', anchor='center', font=('Carlito', 120, 'bold'))


# posLabel = Label(root, text='', font=('Carlito', 225, 'bold'), bg="#f6a0a0")
# posLabel.place(relx=0.5, rely=0.3, anchor='center')

# stateLabel = Label(root, text='', font=('Carlito', 80), fg='#5b5b5b')
# stateLabel.place(relx=0.15, rely=0.3, anchor='center')

# unitLabel = Label(root, text='m', font=('Carlito', 80), fg='#5b5b5b')
# unitLabel.place(relx=0.85, rely=0.3, anchor='center')

# productoraLabel = Label(root, text='PRODUCTORA', font=('Carlito', 75))
# productoraLabel.place(relx=0.5, rely=0.70, anchor='center')

# proyectoLabel = Label(root, text='PROYECTO', font=('Carlito', 75))
# proyectoLabel.place(relx=0.5, rely=0.85, anchor='center')

# guiStateLabel = Label(root, text='offset', font=('Carlito', 75), fg='red')

zigzagImg = Image.open('./zigzag.png')
zigzagImg = zigzagImg.resize((250, 250))
zigzagImg = ImageTk.PhotoImage(zigzagImg)
zigzagLogo = Label(root, image = zigzagImg)

zigzagLogo.place(relx=0.5, rely=0.2, anchor='c')

threading.Thread(target=connectSerial).start()

threading.Thread(target=create_ws).start()

print("kdkdkskfksdkf")

plotPos()

root.bind('<KeyPress-r>',requestHoming)
# root.bind('<KeyPress-r>', requestReset) 
# root.bind('<KeyPress-j>', requestJogTemp)
root.bind('<KeyPress-a>', introduceOffset)
root.bind('<KeyPress-s>', unitSwitch)
root.bind('<KeyPress-x>', focusSwitch)

root.bind('<KeyPress-1>', lambda event: numCallback('1'))
root.bind('<KeyPress-2>', lambda event: numCallback('2'))
root.bind('<KeyPress-3>', lambda event: numCallback('3'))
root.bind('<KeyPress-4>', lambda event: numCallback('4'))
root.bind('<KeyPress-5>', lambda event: numCallback('5'))
root.bind('<KeyPress-6>', lambda event: numCallback('6'))
root.bind('<KeyPress-7>', lambda event: numCallback('7'))
root.bind('<KeyPress-8>', lambda event: numCallback('8'))
root.bind('<KeyPress-9>', lambda event: numCallback('9'))
root.bind('<KeyPress-0>', lambda event: numCallback('0'))
root.bind('<KeyPress-l>', lambda event: numCallback('.'))
root.bind('<KeyPress-v>', clearInput)
root.bind('<KeyPress-KP_Enter>', enterCallback)

root.bind('<KeyPress-d>', lambda event: diffCallback('plus'))
root.bind('<KeyPress-f>', lambda event: diffCallback('minus'))
root.bind('<KeyPress-g>', lambda event: diffCallback('500'))
root.bind('<KeyPress-h>', lambda event: diffCallback('100'))
root.bind('<KeyPress-j>', lambda event: diffCallback('10'))
root.bind('<KeyPress-k>', lambda event: diffCallback('1'))

root.bind('<KeyPress-z>', lambda event: encoderCallback('-'))
root.bind('<KeyPress-c>', lambda event: encoderCallback('+'))


root.update()

root.mainloop()
