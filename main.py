import network
import time
import asyncio
import sys
from math import exp, pow

# import os
# print(os.uname())

import neopixel
from machine import Pin

led = Pin("LED", Pin.OUT)

timezone = +2


### Wifi and connection setup

print("checking wifi.cfg . . . ")
try:
    with open("wifi.cfg") as fid:
        ssid = fid.readline().strip()
        password = fid.readline().strip()
except OSError as e:
    print("Error reading wifi.txt: ", e)
    sys.exit()
    
    
async def connect():
    """Coroutice that runs forever, retrying to connect to wifi if it is lost."""
    led.off()

    network.hostname("picolights")
    wlan = network.WLAN(network.STA_IF)
    while True:
        print("checking wifi connection . . .")
        if not wlan.isconnected():
            led.off()
            wlan.deinit()
            while not wlan.isconnected():
                print(f"connecting to {ssid} . . . ")
                await asyncio.sleep(5)
                wlan.active(True)
                wlan.connect(ssid, password)
        else:
            print(wlan.ifconfig())
            led.on()
            await asyncio.sleep(60)


### Webserver

main_page = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, initial-scale=1.2">
    <title>Pico Lights!</title>
</head>
<body>
    <h1>Pico Lights!</h1>
    
    <p>Current state: {state}</p>
    
    <p>{current_time}</p>
    
    <form method="GET">
        <label>Program:</label><br>
        <div>
            <input type="radio" id="red" name="program" value="red">
            <label for="red">Red</label>
        </div><div>
            <input type="radio" id="green" name="program" value="green">
            <label for="green">Green</label>
        </div><div>
            <input type="radio" id="blue" name="program" value="blue">
            <label for="blue">Blue</label>
        </div><div>
            <input type="radio" id="white" name="program" value="white">
            <label for="white">White</label>
        </div><div>
            <input type="radio" id="clock" name="program" value="clock">
            <label for="clock">Clock</label>
        </div><div>
            <input type="radio" id="dim" name="program" value="dim">
            <label for="red">Dim</label>
        </div><div>
            <input type="radio" id="wakeup" name="program" value="wakeup">
            <label for="wakeup">Wake up</label>
        </div><div>
            <input type="radio" id="hare" name="program" value="hare">
            <label for="hare">Hare</label>
        </div>
        <br>
        <button type="submit" name="light" value="on">On</button>
        <button type="submit" name="light" value="off">Off</button>
    </form>
</body>
</html>
"""

state = {"light": "off", "program": None}

def parse_request(line):
    verb, path, ver = line.split()
    path, query = path.split("?") if "?" in path else (path, "")
    if query:
        q = dict([[x for x in p.split("=")] for p in query.split("&")])
    else:
        q = {}
        
    return (verb, path, q, ver)
    

async def web_handler(read_stream, write_stream):
    global state, state_changed
    
    print(f"Connection from {read_stream.get_extra_info('peername')}")
    buf = await read_stream.readline()
    print(f"    got data: {buf}")
    line = buf.decode().strip()
    if line.startswith("GET"):
        verb, path, query, ver = parse_request(line)        
        print("    parsed from request: ", verb, path, query, ver)
        
        if "light" in query:
            state["light"] = query["light"]
            state_changed = True
            
        if "program" in query:
            state["program"] = query["program"]
            state_changed = True
    else:
        await close(read_stream, write_stream)
        return        
        
    while buf:
        buf = (await read_stream.readline()).strip()
        print(f"    got data: {buf}")
    
    if path == "/":
        content = main_page.encode().format(state=state, current_time=format_current_time())
        length = len(content)
        write_stream.write(f"{ver} 200 OK\r\nContent-Type: text/html\r\nContent-Length: {length}\r\n\r\n")
        write_stream.write(content)
    else:
        write_stream.write(f"{ver} 404 NOT FOUND\r\n\r\n\r\n")
        
    await write_stream.drain()
    await close(read_stream, write_stream)
    

async def close(read_stream, write_stream):
    read_stream.close()
    write_stream.close()
    await read_stream.wait_closed()
    await write_stream.wait_closed()
            

### neopixel 14 LED RGB ring

state_changed = False
dpin = Pin(18, Pin.OUT)
brightness = 1.0

r_factor = 1.0
g_factor = 0.8
b_factor = 0.8

num_leds = 24
# responds to "state"

def gamma(c):
    return (pow(c/255, 2.2)*255)

def color( c ):
    r, g, b = c
    return (
        int(gamma(brightness*r_factor*r)),
        int(gamma(brightness*g_factor*g)),
        int(gamma(brightness*b_factor*b))
    )


class program_clock():
    
    def __init__(self, ring: neopixel.NeoPixel):
        self.ring = ring
        
        
    def tick(self):
        y, m, d, hr, mn, ss, wd, yd = time.gmtime()
        hr = hr%12 + timezone
        
        def dist(i, j):
            return min((i-j)%24, (j-i)%24)
        
        # map 60 seconds to 24 pixels.
        center = 24.0*ss/60.0
        reds = [int(255*pow(3,-dist(center, ii))) for ii in range(24)]
        
        # map 60 minutes to 24 pixels.
        center = 24.0 * (mn + ss/60.0) / 60.0
        greens = [int(255*pow(3,-dist(center, ii))) for ii in range(24)]
        
        # map 24 hours to 24 pixles.
        center = 24.0*(hr + (mn + ss/60.0)/60.0)/12
        blues = [int(255*pow(3,-dist(center, ii))) for ii in range(24)]
        
        for ii, c in enumerate(zip(reds, greens, blues)):
            self.ring[ii] = color(c)
    
        self.ring.write()


class program_hare():
    
    def __init__(self, ring: neopixel.NeoPixel):
        self.ring = ring
        self.r = 0
        self.g = 0
        self.b = 0
        
        
    def tick(self):
        self.r = (1/2 + self.r) % 24
        self.g = (1/3 + self.g) % 24
        self.b = (1/4 + self.b) % 24
        
        self.ring.fill( (0, 0, 0) )
        
        r,g,b = self.ring[int(self.r)]
        self.ring[int(self.r)] = (int(brightness * 255), g, b)
        
        r,g,b = self.ring[int(self.g)]
        self.ring[int(self.g)] = (r, int(brightness * 255), b)
        
        r,g,b = self.ring[int(self.b)]
        self.ring[int(self.b)] = (r, g, int(brightness * 255))
        
        self.ring.write()


class program_wakeup():
    
    # makes assumptions that you want to wake up in the morning, which in
    # you timezone boviously means the start time is before your end time, right?
    
    def __init__(self, ring: neopixel.NeoPixel, start_time=(05, 30), end_time=(06, 15)):
        self.ring = ring
        
        h,m = start_time
        self.start_time = h*3600 + m*60
        
        h,m = end_time
        self.end_time = h*3600 + m*60
        
        self.now = self.start_time - 600
        

    def tick(self):
        y, m, d, hr, mn, ss, wd, yd = time.gmtime()        
        hr += timezone
        
        now = hr * 3600 + mn * 60 + ss
#        now = self.now
        
        if now-25*60 < self.end_time:
            tf = (now-self.start_time) / (self.end_time-self.start_time)
            r = 255*(1 / (1 + exp(-6*(tf-0.3))))
            g = 255*(1 / (1 + exp(-6*(tf-0.5))))
            b = 255*(1 / (1 + exp(-6*(tf-0.8))))
        else:
            r, g, b = 0, 0, 0
        
        print(f"{now//3600}:{(now%3600)//60} {r:02.02f} {g:02.02f} {b:02.02f}")
        
        self.ring.fill(color( (int(r), int(g), int(b)) ))
        self.ring.write()
        self.now += 30


class program_null():
    def tick(self):
        pass

        
async def ring24():
    global state, state_changed, brightness
        
    ring = neopixel.NeoPixel(dpin, num_leds)
    
    print("starting 24 NeoPixel Ring routine")

    pc = program_null()
    while True:
        while not state_changed:
            pc.tick()
            await asyncio.sleep(1.0)
            
        print("state changed!")
        state_changed = False
           
        program = state["program"]
        light = state["light"]
        pc = program_null()
        if light == "on":
            print(f"light is on, {program}")
            if program == "red":
                ring.fill(color( (255, 0, 0) ))
                ring.write()
            elif program == "green":
                ring.fill(color( (0, 255, 0) ))
                ring.write()
            elif program == "blue":
                ring.fill(color( (0, 0, 255) ))
                ring.write()
            elif program == "white":
                ring.fill(color( (255, 255, 255) ))
                ring.write()
            elif program == "dim":
                ring.fill(color( (64, 36, 1) ))
                ring.write()
            elif program == "clock":
                pc = program_clock(ring)
                pc.tick()
            elif program == "wakeup":
                pc = program_wakeup(ring)
                pc.tick()
            elif program == "hare":
                pc = program_hare(ring)
                pc.tick()
        else:
            pc = program_null()
            print("light is off")
            ring.fill( (0, 0, 0) )
            ring.write()


### NTP Time
async def setNtpTime():
    import ntptime
    ntptime.timeout = 3
    waitTime = 5
    while True:
        try:
            ntptime.settime()
            print("set time:", time.gmtime(time.time()))
            await asyncio.sleep(2*3600)
        except OSError as e:
            print("Could not get time:", e, f"waiting {waitTime}s before checking again")
            await asyncio.sleep(waitTime)
            waitTime = min(waitTime * 15 // 10, 600)
            
            
def format_current_time():
    y, m, d, hr, mn, ss, wd, yd = time.gmtime()
    return f"{y}/{m:02d}/{d:02d} {hr:02d}:{mn:02d}:{ss:02d} UTC"


async def main():
    
    # start reconnection loop
    connector = asyncio.create_task(connect())
    
    # set time from the internet
    ntpTimeTask = asyncio.create_task(setNtpTime())
    
    # 24 ring led
    ringTask = asyncio.create_task(ring24())
    
    # start web server
    server = await asyncio.start_server(web_handler, "0.0.0.0", 80)

    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":    
    asyncio.run(main())
    print("done, somehow")
    led.off()



