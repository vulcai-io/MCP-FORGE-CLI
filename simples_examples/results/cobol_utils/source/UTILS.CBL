      * Small utility module used as a codebase example for mcp-forge.
      * Written as modern, isolated COBOL subprograms (PROGRAM-ID with an
      * explicit PROCEDURE DIVISION USING <inputs...> <output> clause) —
      * each one has its own parameters and output, no shared global
      * state between calls, unlike the historical monolithic style of a
      * single PROCEDURE DIVISION full of paragraphs.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. IS-PRIME.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-I            PIC 9(4).
       LINKAGE SECTION.
       01 LS-N            PIC 9(4).
       01 LS-RESULT       PIC 9.
       PROCEDURE DIVISION USING LS-N LS-RESULT.
           IF LS-N < 2
               MOVE 0 TO LS-RESULT
           ELSE
               MOVE 1 TO LS-RESULT
               PERFORM VARYING WS-I FROM 2 BY 1
                   UNTIL WS-I * WS-I > LS-N
                   IF FUNCTION MOD(LS-N, WS-I) = 0
                       MOVE 0 TO LS-RESULT
                   END-IF
               END-PERFORM
           END-IF
           GOBACK.
       END PROGRAM IS-PRIME.

       IDENTIFICATION DIVISION.
       PROGRAM-ID. FACTORIAL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-I2           PIC 9(4).
       LINKAGE SECTION.
       01 LS-N2           PIC 9(4).
       01 LS-RESULT2      PIC 9(9).
       PROCEDURE DIVISION USING LS-N2 LS-RESULT2.
           MOVE 1 TO LS-RESULT2
           PERFORM VARYING WS-I2 FROM 2 BY 1
               UNTIL WS-I2 > LS-N2
               MULTIPLY LS-RESULT2 BY WS-I2 GIVING LS-RESULT2
           END-PERFORM
           GOBACK.
       END PROGRAM FACTORIAL.

       IDENTIFICATION DIVISION.
       PROGRAM-ID. REVERSE-STRING.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-I3           PIC 9(4).
       LINKAGE SECTION.
       01 LS-S            PIC X(50).
       01 LS-R            PIC X(50).
       PROCEDURE DIVISION USING LS-S LS-R.
           MOVE SPACES TO LS-R
           PERFORM VARYING WS-I3 FROM 1 BY 1 UNTIL WS-I3 > 50
               MOVE LS-S(WS-I3:1) TO LS-R(51 - WS-I3:1)
           END-PERFORM
           GOBACK.
       END PROGRAM REVERSE-STRING.
