# SERCOM
SERial COMmunication Handler Python Script

sercom enables automated and manual test sequence on Serial port to configure and monitor Serial modem devices. The Python Script shall be maintained as version/platform agnostic.

## Platform and Environment
sercom Python script is developed to support following Python versions.
1. 2.7 - Older, famous and still being used widely in many organizations
2. 3.x - Newer, emerging and futuristic with more features

As it's scripted in Python, sercom is OS-agnostic. But of course the serial port identifiers may vary while using sercom on different OS's. e.g. COM6 on Windows OS may be seen as /dev/ttyUSB3 on Linux OS. It's upto the user to input proper port identifier.

## Serial Port Configuration file
sercom mandates an input serial port configuration for the script to configure and perform serial IO over the given port. It is specified as '-c \<port-config-filename\>.conf'. 

### Syntax of Port Configuration file
The general syntax on port-conf file is as briefed below:
* No spaces are expected at the start of line, any such lines discarded if present
* Any line starting with '#' is considered as comment and will not be processed, and so any line starting without '#' will be processed as Port IO configuration.
* Any Port IO configuration line must in following Key-Value-Pair (KVP) format -
`key=value`
* There should be only one KVP per line.
* 'key' parameter name MUST be of 6 character length only.
* 'value' can be integer or floating point or string.
* Anything after '=' in a KVP is considered as value, hence quotes and spaces are also taken as part of value. So it's advised not to enclose value with quotes and use spaces after '=' unless required.
e.g. baudrt=115200

Following explains each parameter and it's usage. sample.conf can be referred as well.

Paramater | Presence | Default | Type/Value/Range | Description
 -------- | -------- | ------- | ---------------- | ----------- 
scvcmd    | Mandated | NA      | string           | Serial Comm Validation (SCV) cmd used after opening port to test serial-send works properly by sending scvcmd string to modem
scvrsp    | Mandated | NA      | string           | Serial Comm Validation (SCV) rsp used after opening port to test serial-recv works properly by matching modem rsp with scvrsp value
sentry    | Mandated | NA      | string           | Sentry string used to mark full modem response. Modem MAY have multiple sentries as per response types. '\r' & '\n' characters are treated as CR & LF
baudrt    | Optional | 115200  | 110, 300, 600, 1200, 2400, 4800, 9600, 14400, 19200, 38400, 57600, 115200, 230400, 460800, 921600 | Baud rate to be configured while opening serial port
bytesz    | Optional | 8       | 5, 6, 7, 8       | Byte size to be configured while opening serial port
parity    | Optional | N       | N for none <br>E for even <br>O for odd <br>M for mark <br>S for space | Parity to be configured while opening serial port
stpbit    | Optional | 1       | 1, 1.5, 2        | Stop bit to be configured while opening serial port
rdtout    | Optional | 0.01    | floating point   | Read timeout to be configured while opening serial port
flowct    | Optional | N       | N for None <br>X for XonXoff <br>R for RtsCts <br>D for DsrDtr | Flow Control to be configured while opening serial port
wrtout    | Optional | 0.01    | floating point   | Write timeout to be configured while opening serial port

NOTES: 
1. NA above means Not Applicable/Available
2. If any mandatory parameter is missing, script will throw an error and exit because it cannot proceed without those parameters.
3. If any optional parameter is missing, script will take a corresponding default value for that parameter and proceed.


## SCOM Automated Test Sequence
sercom accepts an optional file containing various sercom-control with syntax and modem commands to automate test sequences. It is specified as '-s \<scom-filename\>.scom'. 

### Syntax of SCOM file
Any line in scom file falls under one of the following categories:
1. scom command - command to control sercom execution (marked as scom\_).
2. comment - Any line starting with '#' is treated as don't care.
3. modem command - if any line is uncommented and is not starting with scom\_, then it is treated as modem command and sent out to modem. So scom writer MUST ENSURE that only modem commands are uncommented and any other alhpanumeric sequence like explanation, description, unwanted-modem-command, etc are commented.

### scom Commands

Following sections detail each scom command. example.scom can be referred as well.

#### scom_enman
When script sees this, Manual Command mode is entered and once ManualCmd mode breaks, the script comes back to processing the next line in current scom file being parsed.

#### scom_enscom
Usage: scom_enscom <path-including-scom-file.scom><br>
If script sees this and if the file-path is valid, sercom will switch to new scom file and run cmds from that scom. If the new scom reaches EOF or 'breaks', sercom will switch back to previously opened scom and continue with that. So a chaining is possible which is explained in a later section.

#### scom_break
When script sees this, it stops current Scom mode - any further commands in file will not be read/executed. It's like a repositionable EOF and can be used during development of advanced Scom test sequences in scom files.

#### scom_loopbegin
Usage: scom_loopbegin [iter=number-of-iterations]<br>
When script sees this, it understands a loop is needed and optionally notes down the number of iterations and breaks the loop after that number of iterations, if iteration count is specified.

#### scom_loopend
When script sees this, it notes that the end of a loop started previously.

#### scom_sleep
Usage: scom_sleep \<n\>[.m]<br>
When script sees this, it sleeps for n seconds and optionally for m milliseconds, if specified.

#### scom_expect
Usage: scom_expect \<action\> \<substring\><br>
TODO<br>
When script encounters above cmd at start of a new line, it tries to match the response buffer of immediately previous modem command. scom supports just one 'scom_expect' per modem command
<action> can be any of the following - 
1. scom_BrkOnMatch - Used for loops, break the loop when match found. If not in loop, this is don't care.
2. scom_BreakOnNoMatch - Used for loops, break the loop when match not found. If not in loop, this is don't care.
3. scom_RmLineOnMatch - Used anywhere in scom, this removes line that contains a pattern (this can help continuous async serial data recv'd to be discarded as and when required).

NOTE: Manual mode supports few of scom commands and they're listed below.
1. scom_break
2. scom_enscom
