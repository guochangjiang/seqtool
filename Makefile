BIN = env/bin
CPP = clang++
CFLAGS = -Wall -std=c++0x -stdlib=libc++ -L/usr/local/lib -I/usr/local/include

all: build

dbload:
	cd database; make

bisearch:
	cd c; make

clean:
	rm -f **/*~
	rm -f #*
	rm -f **/*.pyc
	rm example/*.html

cleanall: clean
	rm -rf develop-egg parts *.egg-info dist

test:
	$(BIN)/nosetests

examples:
	cd example; make

build: bisearch
	cd input; make build

pdf: source.pdf
source.pdf: seqtool/*.py seqtool/**/*.py
	enscript seqtool/*.py seqtool/**/*.py --font=Courier6 --highlight=python --line-numbers --landscape --columns=2 --color -o source.ps
	pstopdf source.ps -o source.pdf
	rm source.ps

.PHONY: test all build clean examples cleanall dbload bsearch

