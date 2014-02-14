CC = gcc

CFLAGS = -Wall -I.
LFLAGS = -lbsmp

OUT = fcs_client

all: $(OUT)

fcs_client: fcs_client.c fcs_client.h
	$(CC) $(CFLAGS) -o $@ $< $(LFLAGS)

clean:
	rm $(OUT)
