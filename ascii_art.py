HEADER = r'''
       .="=.
     _/.-.-.\_     _        P E S A R A N   L A B
    ( ( o o ) )    ))       ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
     |/  "  \|    //         BMI Training
      \'---'/    //
     /`"""`\\  ((
    / /_,_\ \\  \\       joystick ctrl
    \_\\_'__/ \  ))             _
    /`  /`~\  |//              {*}
   /   /    \  /                |
,--`,--'\/\    /               /|\
 '-- "--'  '--'               / | \
'''

MONKEY_FACES = {
    "happy": (
        "o.---.o\n"
        "(o   o)\n"
        "( \\_/ )\n"
        " '---' "
    ),
    "excited": (
        "o.---.o\n"
        "(* . *)\n"
        "( owo )\n"
        " '---' "
    ),
    "sleepy": (
        "o.---.o\n"
        "(- . -)\n"
        "(  ~  )\n"
        " '---' "
    ),
    "cheeky": (
        "o.---.o\n"
        "(o . ^)\n"
        "( \\_/ )\n"
        " '---' "
    ),
    "surprised": (
        "o.---.o\n"
        "(O . O)\n"
        "(  o  )\n"
        " '---' "
    ),
    "grumpy": (
        "o.---.o\n"
        "(> . <)\n"
        "( >_< )\n"
        " '---' "
    ),
    "cool": (
        "o.---.o\n"
        "(= . =)\n"
        "( -_- )\n"
        " '---' "
    ),
    "sweet": (
        "o.---.o\n"
        "(^ . ^)\n"
        "( uwu )\n"
        " '---' "
    ),
}

STATE_LABELS = {
    "ready":     "(^.^)ノ  ready",
    "recording": "(^.^)ノ  recording started   [ ● REC ]",
    "stopped":   "( -.- )  recording stopped   [ ■ STP ]",
    "juice":     "(*^.^*)  juice reward!        [ ~ JCE ]",
    "waiting":   "( ._. )  waiting / idle",
    "trial":     "( >_< )  trial running",
}
