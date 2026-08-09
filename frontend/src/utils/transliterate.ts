import cyrillicToTranslit from 'cyrillic-to-translit-js'

// User.last_name is stored in Cyrillic (Russian names) -- jersey nameplates
// use Latin letters, same convention as real hockey jerseys regardless of
// league. Uses cyrillic-to-translit-js (a small, tested, dependency-light
// library) rather than a hand-rolled letter table -- transliteration has
// enough edge cases (е -> "ye" at a word's start but "e" mid-word, ц -> ts,
// щ -> shch, case handling, ...) that guessing at a mapping risks silently
// misspelling someone's name.
const translit = cyrillicToTranslit()

export function transliterate(input: string): string {
  return translit.transform(input)
}
