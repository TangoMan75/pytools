#!/bin/bash

#/*
# * This file is part of TangoMan package.
# *
# * Copyright (c) 2026 "Matthias Morin" <mat@tangoman.io>
# *
# * This source file is subject to the MIT license that is bundled
# * with this source code in the file LICENSE.
# */

./installer.py uninstall -vvv bookmarks.py conv-*.py g*.py history-*.py jira-rest.py md-*.py models.py moments.py
./installer.py install -vvv bookmarks.py conv-*.py g*.py history-*.py jira-rest.py md-*.py models.py moments.py
