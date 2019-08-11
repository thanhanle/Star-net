Name: 					Andrew Le
partner: 				Alex Chan
email: 					andrew7@gatech.edu
date: 					November 11, 2018
assignment: 			"The Project" - Reliable message broacasting over a self-organized dynamic star network
files and desctiption: 	star-node.py (main project program that contains the class of a starnode that forms the starnet)
						sample.txt (sample output of the program)
						README.txt (logistics and description of the program)
						3251-project-Fall18-version1.pdf (assignment pdf)
						img1.jpg (image to send to other odes)


instruction to compile and run program: 
This program is in Python and uses version 3.6.5 and was programed on Windows 10.
To first compile and run the program, you type: python star-node.py <name> <local-port> <PoC-address> <PoC-port> <N>
you open up N programs with different IP addresses and ports and the starnet should be formed. Type: send "<message>" to send your message to all the other stars in the starnet (has to be in double quotations). To send an image to other star-nodes type: send <image> to send image to other star nodes. image should be the name of the file.


design documentation:
pending to be changed until the final milestone


bugs and limitations: 
the current implementation does not implement Churn and Keep-Alive mechanisms. The program is also not scalable for a lot of different stars like 1,000 stars since the implementation assumes the queue would not be filled up.