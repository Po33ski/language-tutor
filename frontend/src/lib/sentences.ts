// A sentence ends with . ! ? or … (optionally followed by closing quotes or brackets),
// then whitespace. Requiring the whitespace keeps "3.5" or a half-streamed "Hello." whole.
const SENTENCE_END = /[.!?…]+["'”’)\]]*\s+/g;

// Shorter "sentences" ("Ok.") are joined with the next one, so each synthesis request
// carries enough text.
const MIN_SENTENCE_LENGTH = 8;

// A period after these does not end the sentence ("Hello, Mr. Smith.").
const ABBREVIATION_END = /\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|etc|e\.g|i\.e)\.$/i;

/**
 * Splits the complete sentences off the start of streamed text. `rest` is the
 * unfinished tail, to be completed by the next chunks.
 */
export function takeSentences(text: string): { sentences: string[]; rest: string } {
  const sentences: string[] = [];
  let start = 0;
  for (const match of text.matchAll(SENTENCE_END)) {
    const end = match.index + match[0].length;
    const sentence = text.slice(start, end).trim();
    if (sentence.length < MIN_SENTENCE_LENGTH || ABBREVIATION_END.test(sentence)) continue;
    sentences.push(sentence);
    start = end;
  }
  return { sentences, rest: text.slice(start) };
}

/** All sentences of a finished text, including a last one without final punctuation. */
export function splitSentences(text: string): string[] {
  const { sentences, rest } = takeSentences(text);
  const tail = rest.trim();
  return tail ? [...sentences, tail] : sentences;
}
