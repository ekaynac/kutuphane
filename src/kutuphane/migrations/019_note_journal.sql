-- docs/24 §20.3: restriction follows derivation after creation. A note's search and AI input are ANDed with the
-- CURRENT values of every journal in its source_books, so `kutuphane journal restrict` on a source journal also
-- tightens the notes derived from it in other journals. source_books always holds the note's own journal.
CREATE VIEW note_journal AS
SELECT n.seq, j.search, j.ai_input
  FROM note n
 CROSS JOIN LATERAL (SELECT bool_and(search) AS search, bool_and(ai_input) AS ai_input
                       FROM journal WHERE book = ANY(n.source_books)) j;
