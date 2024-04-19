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
import logging
import os
import cv2
from dataclasses import dataclass

import time

logger = logging.getLogger(__name__)
logging.basicConfig(filename=os.path.expanduser('~')+'/example.log', encoding='utf-8', level=logging.DEBUG)
logging.getLogger().addHandler(logging.StreamHandler())

@dataclass
class Employee:
    name: str = ''
    filename: str = ''
    img: ... = None

class Table:
    def __init__(self,root):
        self.e = [ [None]*debugList_columns for _ in range(debugList_rows) ]
        for i in range(debugList_rows):
            for j in range(debugList_columns):
                self.e[i][j] = Label(root, text = debugList[i][j], width=20, fg='blue',
                               font=('Arial',16,'bold'))
                self.e[i][j].grid(row=i, column=j)
                # self.e[i][j].insert(END, debugList[i][j])
    def remove(self, root):
        global debugTable
        for i in range(debugList_rows):
            for j in range(debugList_columns):  
                self.e[i][j].grid_remove()
        debugTable = None
        
    def update(self,root):
        global debugList
        for i in range(debugList_rows):
            self.e[i][1].configure(text=debugList[i][1]) 

class Timer:
    def __init__(self):
        self._start_time = None
    def start(self):
        if self._start_time is not None:
            log.error(f"Timer is running. Use .stop() to stop it")
        self._start_time = time.perf_counter()

    def stop(self):
        if self._start_time is None:
            log.error(f"Timer is not running. Use .start() to start it")
        elapsed_time = time.perf_counter() - self._start_time
        self._start_time = None
        return elapsed_time



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



def WPosToMPos (position):
    position = position -5177 -1054 - offset*1000
    return position

def MPosToWPos (position):
    position = position +5177 +1054 + offset*1000
    return position

def sendStream(text):
    global focusMain
    global wsapp
    logger.info(f'FocusMain: {focusMain}: Sent: {text}')
    if focusMain:
        if comPort:
            comPort.write(text.encode())
    elif not focusMain:
        if WSConnected:
            wsapp.send(text.encode())

def unitCorrection(pos):
    if unit == ' ft':
        pos = pos * 3.28084
    else:
        pos = pos
    return pos

def plotPos():
    global displayProd
    global displayProy
    global unit
    if guiState == 'distance':
        showOffsetText(False)
        try:
            aux = unitCorrection(abs(MPosToWPos(Mpos)))
            displayPos = '{:.3f}'.format((aux)/1000)
            updatePosText(displayPos)
            # canvas.itemconfig(posText, text=displayPos+' m')
        except:
            logger.error('Tried to plot a Pos that is not a Float')
    elif guiState == 'target':
        showOffsetText(False)
        updatePosText(userInput)
    elif guiState == 'offset':
        showOffsetText(True)
        if not userInput == 'None':
            updatePosText(userInput)
    root.after(50, plotPos)

def askSerial():
    if comPort:
        try:
            comPort.write('?'.encode())
        except:
            logger.warning("Could not wirte ?")
    root.after(100,askSerial)

def askWebSocket():
    if WSConnected:
        try:
            wsapp.send("?\n".encode())
        except:
            logger.warning("WS: Could not send ?")
    root.after(1000,askWebSocket)

def ReceiveThread():
    global wsapp
    while comPort:
        try:
            inWaiting = comPort.inWaiting()
            if inWaiting > 2:
                global lines
                global resetNeed
                global mainGrblState

                global Mpos
                global mainMqttConnected
                global mainPairConnected
                global mainHomed
                global mainAllowMovement
                global mainPins
                lines = comPort.readline().decode('utf-8')
                
                listOfStates = ['Idle', 'Run', 'Hold', 'Jog', 'Alarm', 'Door', 'Check', 'Home', 'Sleep']
                for s in listOfStates:
                    if s in lines:
                        mainGrblState = s
                ##Checks if grbl needs a reset

                if 'Reset to continue' in lines:
                    resetNeed = True

                if re.match(r'\<([^]]+)\>',lines):
                    mainPins = 'None'
                    fields = lines.split('<')[1]
                    fields = fields.split('>')[0]
                    fields = fields.split('|')
                    for field in fields:
                        if 'Mqtt' in field:
                            mainMqttConnected = re.split(':',field)[1]
                        elif 'AlwMov' in field:
                            mainAllowMovement = re.split(':',field)[1]
                        elif 'Pair' in field:
                            mainPairConnected = re.split(':',field)[1]
                        elif 'Homed' in field:
                            mainHomed = re.split(':',field)[1]
                        elif 'Pos' in field:
                            aux = re.split(r',|:',field)[1]
                            aux = float(aux)
                            Mpos = aux
                        elif 'Pn' in field:
                            mainPins = re.split(':',field)[1]
                else:
                    logger.warning('Message without <> formating:')
                    logger.warning('\t'+lines)
            else:
                time.sleep(0.01)
        except:
            logger.error('Serial port disconnected')
            connectSerial()
            break


def releaseX(event):
    global xTimer
    global debugOverlay
    stopTime = xTimer.stop()
    logger.debug(f'Stop time: {stopTime:.4f}')
    if stopTime > 0.395:
        if debugOverlay == False:
            debugOverlay = True
            showDebugOverlay()
        else:
            debugOverlay = False


def requestHoming(event):
    global wsapp
    if WSConnected:
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
    logger.info('Sent: reset\n')
    
def requestJogTemp(event):
    comPort.write('$J=G91 G21 X-449.000 F34800\n'.encode())
    logger.info('Sent: request jog\n')

def requestJog(target, absolute):
    if unit == ' ft':
        target = float(target)
        target = target / 3.28084
        target = '{:.4f}'.format((abs(target)))
    if absolute:
        target = (float(target))*1000
        target = WPosToMPos(target)
        jogCommand = '$J=G90 G21 X'+'{:.3f}'.format(target)+ ' F34800\n'
        sendStream(jogCommand)
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
    logger.debug("Number pressed: " + num)
    if guiState == 'distance':
        guiState = 'target'
    if guiState == 'offset' or guiState == 'target':
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
        sendStream(jogCommand)
        sign = None


def updateDebugList():
    global debugList
    mainDebugList = [('MAIN', 'MAIN'),
        ('grblState', mainGrblState),
        ('mainMqttConnected', mainMqttConnected),
        ('mainPairConnected', mainPairConnected),
        ('mainHomed', mainHomed),
        ('mainAllowMovement', mainAllowMovement),
        ('mainPins', mainPins)]
    secDebugList = [('SEC', 'SEC'),
        ('WSConnected', WSConnected),
        ('grblState', secGrblState),
        ('mainMqttConnected', secMqttConnected),
        ('mainPairConnected', secPairConnected),
        ('mainHomed', secHomed),
        ('mainAllowMovement', secAllowMovement),
        ('secPins', secPins)]

    pythonDebugList = [('PYTHON', 'PYTHON'),
        ('WSConnected', WSConnected),
        ('FocusMain', focusMain)]

    debugList = mainDebugList + secDebugList + pythonDebugList



def showDebugOverlay():
    global debugTable
    # show overlay
    if not debugTable:
        debugTable = Table(root)
    else:
        updateDebugList()
        debugTable.update(root)
    if debugOverlay:
        root.after(100, showDebugOverlay)
    else:
        debugTable.remove(root)
        logger.info('Quiting debug overlay')

def encoderCallback(input):
    jogCommand = '$J=G91 G21 X'+input+'10 F34800\n'
    sendStream(jogCommand)

def enterCallback(event):
    global guiState
    global userInput
    global offset
    if userInput == 'None':
        clearInput(event)
    if guiState == 'target':
        if not userInput == 'None':
            requestJog(userInput, True)
            userInput = 'None'
            guiState = 'distance'
    elif guiState == 'offset':
        if not userInput == 'None':
            offset = float(userInput)
            userInput = 'None'
            guiState = 'distance'

def updateuserInput(num):
    global userInput
    logger.debug('Previous user input: ' + userInput)
    if userInput == 'None':
        userInput = num
    elif len(userInput) < 5:
        userInput = userInput + num
    logger.debug('Tried to append number: ' + num)
    logger.debug('New user input: ' + userInput)

def clearInput(event):
    global guiState
    global userInput
    logger.debug('Flushed user input')
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
        plotProd

def plotProd():
    if prod == '' and proy == '':
        #place ZZ logo
        zigzagLogo.place(relx=0.5, rely=0.2, anchor='c')
    else:
        zigzagLogo.place_forget()
        #remove ZZ logo
        #add text fields

def getEmployees():
    images = []
    
    for filename in os.listdir('./Employees'):
        employee = Employee()
        employee.img = cv2.imread(os.path.join('./Employees',filename))
        if employee.img is not None:
            employee.filename = filename
            employee.name = parseEmployeeName(filename)
            images.append(employee)
    return images

def parseEmployeeName(filename):
    return filename.replace('-', ' ').rsplit('.',1)[0]

def connectSerial():
    global comPort
    while True:
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            if 'CP2102' in p.description:
                port = p.device
        try:
            # comPort = serial.Serial('/dev/ttyUSB2',115200)
            comPort = serial.Serial(port,115200)
        except:
            time.sleep(1)
        if comPort:
            logger.debug('Calling RecieveThread')
            ReceiveThread()

reply_timeout = 10
ping_timeout = 5
sleep_time = 5
url = 'ws://192.168.0.31:80'

def on_open(ws):
    global WSConnected
    WSConnected = True
    logger.info('WS successfully connected')

def on_message(ws, message):
    global secResetNeed
    global secGrblState

    global secMpos
    global secMqttConnected
    global secPairConnected
    global secHomed
    global secAllowMovement
    global secPins

    listOfStates = ['Idle', 'Run', 'Hold', 'Jog', 'Alarm', 'Door', 'Check', 'Home', 'Sleep']
    for s in listOfStates:
        if s in message:
            secGrblState = s

    if 'Reset to continue' in message:
        secResetNeed = True

    if re.match(r'\<([^]]+)\>',message):
        secPins = 'None'
        fields = message.split('<')[1]
        fields = fields.split('>')[0]
        fields = fields.split('|')
        for field in fields:
            if 'Mqtt' in field:
                secMqttConnected = re.split(':',field)[1]
            elif 'AlwMov' in field:
                secAllowMovement = re.split(':',field)[1]
            elif 'Pair' in field:
                secPairConnected = re.split(':',field)[1]
            elif 'Homed' in field:
                secHomed = re.split(':',field)[1]
            elif 'Pos' in field:
                aux = re.split(r',|:',field)[1]
                aux = float(aux)
                secMpos = aux
            elif 'Pn' in field:
                secPins = re.split(':',field)[1]
    else:
        logger.warning('Message without <> formating:')
        logger.warning('\t'+lines)

def on_close(ws, close_status_code, close_msg):
    global WSConnected
    WSConnected = False

def create_ws():
    global wsapp
    while True:
        try:
            websocket.enableTrace(False)
            wsapp = websocket.WebSocketApp(url,
                                        on_message = on_message)
            wsapp.on_open = on_open
            wsapp.on_message = on_message
            wsapp.run_forever(skip_utf8_validation=True,ping_interval=0,ping_timeout=8)
        except Exception as e:
            # gc.collect()
            logger.error("Websocket connection Error  : {0}".format(e))                    
        
        logger.error("Reconnecting websocket  after 5 sec")
        time.sleep(5)

def unitSwitch(event):
    global unit
    global offset
    if unit == ' m':
        unit = ' ft'
        # offset = offset * 3.28084
    else:
        unit = ' m'
        # offset = offset / 3.28084

def focusSwitch(event):
    global focusMain
    global xTimer
    xTimer.start()
    if focusMain:
        focusMain = False
    elif not focusMain:
        focusMain = True
    else:
        focusMain = True

def plotArrows():
    logger.debug('Plot arrows')
    # call it when sending any jog thing.
    # maybe animate it
    #if target > pos:
        # green arrow
    # else:
    #     red arrow

## Config params
ScreenWidth = 2560
ScreenHeight = 1600

# ScreenWidth = 1920
# ScreenHeight = 1080

## Initialize pos and lines. It is being updated from the other thread,
## Careful with multithread modification
Mpos = 0.0
lines = ''
alarmState = 0
resetNeed = False
mainGrblState = ''
guiState = 'distance'
offset = 0
userInput = 'None'
comPort = ''
unit = ' m'
sign = None
wsapp = None
focusMain = True
debugOverlay = False
xTimer = Timer()
debugTable = False
mainMqttConnected = False
mainPairConnected = False
mainHomed = False
mainAllowMovement = False
mainPins = ''
WSConnected = False

secGrblState = ''
secMqttConnected = False
secPairConnected = False
secHomed = False
secAllowMovement = False
secPins = ''

updateDebugList()

debugList_rows = len(debugList)
debugList_columns = len(debugList[0])



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

employeeList = getEmployees()

root = Tk()
root.geometry(str(ScreenWidth)+'x'+str(ScreenHeight))
root.attributes("-fullscreen", True)  # substitute `Tk` for whatever your `Tk()` object is called

canvas = Canvas(root, bg="white", width=ScreenWidth, height=ScreenHeight)
canvas.place(x=0,y=0)

canvas.create_rectangle(0, 0, ScreenWidth, ScreenHeight*0.45, fill="#f6a0a0", outline='')

employeeCanvas = Canvas(root, bg="#f6a0a0", width=0.4*ScreenWidth, height=0.1*ScreenHeight)
employeeCanvas.place(x=ScreenWidth/2,y=ScreenHeight*0.4, anchor='center')

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

plotPos()
askWebSocket()
askSerial()

root.bind('<KeyPress-r>',requestHoming)
# root.bind('<KeyPress-r>', requestReset) 
# root.bind('<KeyPress-j>', requestJogTemp)
root.bind('<KeyPress-a>', introduceOffset)
root.bind('<KeyPress-s>', unitSwitch)
root.bind('<KeyPress-x>', focusSwitch)
root.bind('<KeyRelease-x>', releaseX)

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
