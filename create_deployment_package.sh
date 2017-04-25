#!/bin/sh
export FN=`date +%s`
export DIRECTORY=dist/$FN
export PIP=pip

mkdir $DIRECTORY || exit 1
cp *.py $DIRECTORY || exit 2
cp requirements.txt $DIRECTORY || exit 3
pushd $DIRECTORY

# Python 2.7 on OSX workaround
export REMOVE_PIP_CONFIG=0
if [[ "$OSTYPE" == "darwin"* ]]; then
	if [ ! -f "~/.pydistutils.cfg" ]; then
		cp -v ../../pydistutils.osx.cfg ~/.pydistutils.cfg
		export REMOVE_PIP_CONFIG=1
	fi
fi

pip install -r requirements.txt -t . || exit 4

if [[ "$REMOVE_PIP_CONFIG" == "1" ]]; then
	rm -v ~/.pydistutils.cfg
fi

7z a -tzip "../${FN}.zip" * || exit 5
echo Succesfully created archive: ${DIRECTORY}.zip

popd

