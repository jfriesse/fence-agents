#!/usr/bin/python

import getopt, sys
import os
import socket
import time
import atexit

from telnetlib import Telnet

TELNET_TIMEOUT=30 #How long to wait for a response from a telnet try
MAX_TRIES = 20

# WARNING!! Do not add code bewteen "#BEGIN_VERSION_GENERATION" and
# "#END_VERSION_GENERATION"  It is generated by the Makefile

#BEGIN_VERSION_GENERATION
RELEASE_VERSION=""
REDHAT_COPYRIGHT=""
BUILD_DATE=""
#END_VERSION_GENERATION

def usage():
  print "Usage:"
  print "fence_rsb [options]"
  print "Options:"
  print "   -a <ipaddress>           ip or hostname of rsb"
  print "   -h                       print out help"
  print "   -l [login]               login name"
  print "   -n [telnet port]         telnet port"
  print "   -p [password]            password"
  print "   -S [path]                script to run to retrieve password"
  print "   -o [action]              reboot (default), off, on, or status"
  print "   -v Verbose               Verbose mode"
  print "   -V                       Print Version, then exit"

  sys.exit (0)

def version():
  print "fence_rsb %s  %s\n" % (RELEASE_VERSION, BUILD_DATE)
  print "%s\n" % REDHAT_COPYRIGHT
  sys.exit(0)

def atexit_handler():
	try:
		sys.stdout.close()
		os.close(1)
	except IOError:
		sys.stderr.write("%s failed to close standard output\n"%(sys.argv[0]))
		sys.exit(1)

def main():
  depth = 0
  POWER_OFF = 0
  POWER_ON = 1
  POWER_STATUS = 2
  POWER_REBOOT = 3

  STATUS_ON = 0
  STATUS_OFF = 2

  power_command_issued = 0 

  address = ""
  login = ""
  passwd = ""
  passwd_script = ""
  action = POWER_REBOOT   #default action
  telnet_port = 3172
  verbose = False
  power_state = None

  standard_err = 2

  result = 0

  #set up regex list
  USERNAME = 0
  PASSWORD = 1
  PROMPT = 2
  STATE = 3
  ERROR = 4
  CONT = 5
  CONFIRM = 6
  DONE = 7

  regex_list = list()
  regex_list.append("user name\s*:")
  regex_list.append("pass phrase\s*:")
  regex_list.append("[Ee]nter\s+[Ss]election[^\r\n]*:")
  regex_list.append("[pP]ower Status:")
  regex_list.append("[Ee]rror\s*:")
  regex_list.append("[Pp]ress any key to continue")
  regex_list.append("really want to")
  regex_list.append("CLOSING TELNET CONNECTION")

  atexit.register(atexit_handler)

  if len(sys.argv) > 1:
    try:
      opts, args = getopt.getopt(sys.argv[1:], "a:hl:n:o:p:S:vV", ["help", "output="])
    except getopt.GetoptError:
      #print help info and quit
      usage()
      sys.exit(2)

    for o, a in opts:
      if o == "-v":
        verbose = True
      if o == "-V":
        version()
      if o in ("-h", "--help"):
        usage()
        sys.exit(0)
      if o == "-l":
        login = a
      if o == "-n":
        telnet_port = a
      if o == "-p":
        passwd = a
      if o == "-S":
        passwd_script = a
      if o  == "-o":
        a_lower=a.lower()
        if a_lower == "off":
          action = POWER_OFF
        elif a_lower == "on":
          action = POWER_ON
        elif a_lower == "status":
          action = POWER_STATUS
        elif a_lower == "reboot":
          action = POWER_REBOOT
        else:
          usage()
          sys.exit(1)
      if o == "-a":
        address = a
    if address == "" or login == "" or (passwd == "" and passwd_script == ""):
      usage()
      sys.exit(1)

  else: #Take args from stdin...
    params = {}
    #place params in dict
    for line in sys.stdin:
      val = line.split("=")
      if len(val) == 2:
        params[val[0].strip()] = val[1].strip()

    try:
      address = params["ipaddr"]
    except KeyError, e:
      os.write(standard_err, "FENCE: Missing ipaddr param for fence_rsb...exiting")
      sys.exit(1)
    
    try:
      login = params["login"]
    except KeyError, e:
      os.write(standard_err, "FENCE: Missing login param for fence_rsb...exiting")
      sys.exit(1)
    
    try:
      if 'passwd' in params:
        passwd = params["passwd"]
      if 'passwd_script' in params:
        passwd_script = params['passwd_script']
      if passwd == "" and passwd_script == "":
        raise "missing password"
    except KeyError, e:
      os.write(standard_err, "FENCE: Missing passwd param for fence_rsb...exiting")
      sys.exit(1)
    
    try:
      telnet_port = params["telnet_port"]
    except KeyError, e:
      pass

    try:
      a = params["option"]
      a_lower=a.lower()
      if a_lower == "off":
        action = POWER_OFF
      elif a_lower == "on":
        action = POWER_ON
      elif a_lower == "reboot":
        action = POWER_REBOOT
    except KeyError, e:
      action = POWER_REBOOT

    ####End of stdin section
  
  
  # retrieve passwd from passwd_script (if specified)
  passwd_scr = ''
  if len(passwd_script):
    try:
      if not os.access(passwd_script, os.X_OK):
        raise 'script not executable'
      p = os.popen(passwd_script, 'r', 1024)
      passwd_scr = p.readline().strip()
      if p.close() != None:
        raise 'script failed'
    except:
      sys.stderr.write('password-script "%s" failed\n' % passwd_script)
      passwd_scr = ''
  
  if passwd == "" and passwd_scr == "":
    sys.stderr.write('password not available, exiting...')
    sys.exit(1)
  elif passwd == passwd_scr:
    pass
  elif passwd and passwd_scr:
    # execute self, with password_scr as passwd,
    # if that fails, continue with "passwd" argument as password
    if len(sys.argv) > 1:
      comm = sys.argv[0]
      skip_next = False
      for w in sys.argv[1:]:
        if skip_next:
          skip_next = False
        elif w in ['-p', '-S']:
          skip_next = True
        else:
          comm += ' ' + w
      comm += ' -p ' + passwd_scr
      ret = os.system(comm)
      if ret != -1 and os.WIFEXITED(ret) and os.WEXITSTATUS(ret) == 0:
        # success
        sys.exit(0)
      else:
        sys.stderr.write('Use of password from "passwd_script" failed, trying "passwd" argument\n')
    else: # use stdin
      p = os.popen(sys.argv[0], 'w', 1024)
      for par in params:
        if par not in ['passwd', 'passwd_script']:
          p.write(par + '=' + params[par] + '\n')
      p.write('passwd=' + passwd_scr + '\n')
      p.flush()
      if p.close() == None:
        # success
        sys.exit(0)
      else:
        sys.stderr.write('Use of password from "passwd_script" failed, trying "passwd" argument\n')
  elif passwd_scr:
    passwd = passwd_scr
  # passwd all set
  
  
  
  try:
    telnet_port = int(telnet_port)
  except:
    os.write(standard_err, ("FENCE: Invalid telnet port: %s\n" % telnet_port))
    sys.exit(1)
    
  ##Time to open telnet session and log in. 
  try:
    sock = Telnet(address.strip(), telnet_port)
  except socket.error, (errno, msg):
    my_msg = "FENCE: A problem was encountered opening a telnet session with " + address
    os.write(standard_err, my_msg)
    os.write(standard_err, ("FENCE: Error number: %d -- Message: %s\n" % (errno, msg)))
    os.write(standard_err, "Firewall issue? Correct address?\n")
    sys.exit(1)

  if verbose:
    #sock.set_debuglevel(10000)
    print  "socket open to %s %d\n" % (address, telnet_port)

  tries = MAX_TRIES
  while 1:
    i, mo, txt = sock.expect(regex_list, TELNET_TIMEOUT)
    if i == ERROR:
      os.write(standard_err,("FENCE: An error was encountered when communicating with the rsb device at %s" % address))
      buf = sock.read_eager()
      os.write(standard_err,("FENCE: The error message is - %s" % txt + " " + buf))
      sock.close()
      sys.exit(1)

    buf = sock.read_eager()
    if i == USERNAME:
      if verbose:
        print "Sending login: %s\n" % login
      sock.write(login + "\r")

    elif i == PASSWORD:
      if verbose:
        print "Sending password: %s\n" % passwd
      sock.write(passwd + "\r")

    elif i == CONT:
      if verbose:
        print "Sending continue char..."
      sock.write("\r")
      time.sleep(2)

    elif i == CONFIRM:
      if verbose:
        print "Confirming..."
      sock.write("yes\r")

    elif i == PROMPT:
      if verbose:
        print "Evaluating prompt...\n"

      if depth == 0:
        sock.write("2\r")
        depth += 1
      elif depth == 1:
        if action == POWER_OFF or action == POWER_REBOOT:
          if power_command_issued == 0:
            if verbose:
              print "Sending power off %s" % address
            sock.write("1\r")
            power_command_issued += 1
            time.sleep(2)
          elif power_command_issued and power_state == 0:
            if verbose:
              print "Power off was successful"
            if action == POWER_OFF:
              depth += 1
              sock.write("0\r")
            else:
              action = POWER_ON
              power_command_issued = 0
              sock.write("\r")
          elif tries > 0:
            if verbose:
              print "Waiting for power off to complete"
            tries -= 1
            sock.write("\r")
            time.sleep(2)
          else:
            os.write(standard_err, "FENCE: Unable to power off server")
            depth += 1
            sock.write("0\r")

        elif action == POWER_ON:
          if power_command_issued == 0:
            if verbose:
              print "Sending power on %s" % address
            sock.write("4\r")
            power_command_issued += 1
            time.sleep(2)
          elif power_command_issued and power_state == 1:
            if verbose:
              print "Power on was successful"
            depth += 1
            sock.write("0\r")
          elif tries > 0:
            if verbose:
              print "Waiting for power on to complete"
            tries -= 1
            sock.write("\r")
            time.sleep(2)
          else:
            os.write(standard_err, "FENCE: Unable to power on server")
            depth += 1
            sock.write("0\r")
      else:
        sock.write("0\r")

    elif i == STATE:
      if buf.find(" On") != (-1):
        power_state = 1
      elif buf.find(" Off") != (-1):
        power_state = 0
      else:
        power_state = None

      if action == POWER_STATUS:
        if verbose:
          print "Determining power state..."
        if power_state == 1:
          print "Server is On"
          result = STATUS_ON
        elif power_state == 0:
          print "Server is Off"
          result = STATUS_OFF
        else:
          os.write(standard_err, ("FENCE: Cannot determine power state: %s" % buf))
          sys.exit(1)
        depth = 2

    elif i == DONE:
      break

    else:
      sock.write("\r")

  sock.close()
  sys.exit(result)

if __name__ == "__main__":
  main()
