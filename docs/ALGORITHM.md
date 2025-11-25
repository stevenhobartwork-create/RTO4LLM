# RTO Algorithm Pseudocode

## Compression Algorithm

```
FUNCTION compress(text, file_extension):
    
    # Step 1: Escape existing tildes
    text = REPLACE_ALL(text, "~", "~~")
    
    # Step 2: Load dictionaries
    global_dict = LOAD_GLOBAL_DICTIONARY()      # ~150 common keywords
    type_dict = LOAD_TYPE_DICTIONARY(file_extension)  # language-specific
    
    # Step 3: Build local dictionary from file
    words = EXTRACT_WORDS(text, min_length=4)
    word_counts = COUNT_FREQUENCIES(words)
    
    # Filter: only words that appear 2+ times and save bytes
    local_dict = {}
    token_index = 0
    FOR word, count IN SORTED_BY_FREQUENCY(word_counts):
        bytes_saved = (LENGTH(word) - 2) * count  # ~N is 2 chars
        IF bytes_saved > 0 AND count >= 2:
            token = "~" + BASE62_ENCODE(token_index)
            local_dict[token] = word
            token_index += 1
        IF token_index >= 200:  # max local dict size
            BREAK
    
    # Step 4: Apply global dictionary (longest tokens first)
    FOR i, word IN ENUMERATE(global_dict):
        token = "~^" + BASE62_ENCODE(i)
        text = REPLACE_WORD_BOUNDARIES(text, word, token)
    
    # Step 5: Apply type dictionary
    FOR i, word IN ENUMERATE(type_dict):
        token = "~*" + BASE62_ENCODE(i)
        text = REPLACE_WORD_BOUNDARIES(text, word, token)
    
    # Step 6: Apply local dictionary
    FOR token, word IN local_dict:
        text = REPLACE_WORD_BOUNDARIES(text, word, token)
    
    # Step 7: Build output with JSON header
    header = JSON_ENCODE({
        "v": "1.2",
        "m": local_dict,
        "ext": file_extension
    })
    
    RETURN header + "\n" + text
```

## Expansion Algorithm

```
FUNCTION expand(compressed_text):
    
    # Step 1: Parse header
    first_newline = FIND_FIRST(compressed_text, "\n")
    header_json = compressed_text[0:first_newline]
    body = compressed_text[first_newline+1:]
    
    header = JSON_DECODE(header_json)
    local_dict = header["m"]
    file_ext = header["ext"]
    
    # Step 2: Load built-in dictionaries
    global_dict = LOAD_GLOBAL_DICTIONARY()
    type_dict = LOAD_TYPE_DICTIONARY(file_ext)
    
    # Step 3: Replace local tokens (~N)
    FOR token, word IN local_dict:
        body = REPLACE_ALL(body, token, word)
    
    # Step 4: Replace type tokens (~*N)
    FOR i, word IN ENUMERATE(type_dict):
        token = "~*" + BASE62_ENCODE(i)
        body = REPLACE_ALL(body, token, word)
    
    # Step 5: Replace global tokens (~^N)
    FOR i, word IN ENUMERATE(global_dict):
        token = "~^" + BASE62_ENCODE(i)
        body = REPLACE_ALL(body, token, word)
    
    # Step 6: Unescape tildes
    body = REPLACE_ALL(body, "~~", "~")
    
    RETURN body
```

## Testing Algorithm

```
FUNCTION test_roundtrip(file_path):
    
    # Read original
    original = READ_FILE(file_path)
    
    # Skip binary files
    IF CONTAINS_NULL_BYTES(original):
        RETURN SKIP
    
    # Detect extension
    ext = GET_FILE_EXTENSION(file_path)
    
    # Compress
    compressed = compress(original, ext)
    
    # Expand
    restored = expand(compressed)
    
    # Verify
    IF restored == original:
        RETURN PASS
    ELSE:
        RETURN FAIL


FUNCTION benchmark(directory, max_files=20000):
    
    files = COLLECT_SOURCE_FILES(directory)
    SHUFFLE(files)
    files = files[0:max_files]
    
    stats = {
        "total_original": 0,
        "total_compressed": 0,
        "pass_count": 0,
        "fail_count": 0,
        "by_type": {},
        "by_size": {}
    }
    
    FOR file IN files:
        result = test_roundtrip(file)
        
        IF result == PASS:
            stats["pass_count"] += 1
            
            original_size = FILE_SIZE(file)
            compressed_size = LENGTH(compress(READ_FILE(file)))
            
            stats["total_original"] += original_size
            stats["total_compressed"] += compressed_size
            
            # Track by file type
            ext = GET_EXTENSION(file)
            UPDATE_STATS(stats["by_type"], ext, original_size, compressed_size)
            
            # Track by size bucket
            bucket = SIZE_BUCKET(original_size)
            UPDATE_STATS(stats["by_size"], bucket, original_size, compressed_size)
            
        ELSE IF result == FAIL:
            stats["fail_count"] += 1
    
    PRINT_RESULTS(stats)


FUNCTION SIZE_BUCKET(size_bytes):
    IF size_bytes < 1024:
        RETURN "<1KB"
    ELSE IF size_bytes < 10*1024:
        RETURN "1-10KB"
    ELSE IF size_bytes < 50*1024:
        RETURN "10-50KB"
    ELSE IF size_bytes < 100*1024:
        RETURN "50-100KB"
    ELSE IF size_bytes < 500*1024:
        RETURN "100-500KB"
    ELSE IF size_bytes < 1024*1024:
        RETURN "500KB-1MB"
    ELSE:
        RETURN "1MB+"
```

## Helper Functions

```
FUNCTION BASE62_ENCODE(n):
    # Encode integer to base62 (0-9, a-z, A-Z)
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    IF n < 62:
        RETURN chars[n]
    ELSE:
        RETURN STRING(n)  # fallback for large indices


FUNCTION REPLACE_WORD_BOUNDARIES(text, word, token):
    # Replace word only at word boundaries (not inside other words)
    # Match: \b{word}\b
    pattern = REGEX("\\b" + ESCAPE(word) + "\\b")
    RETURN REGEX_REPLACE(text, pattern, token)


FUNCTION EXTRACT_WORDS(text, min_length):
    # Extract words matching [a-zA-Z_][a-zA-Z0-9_]{min_length-1,}
    pattern = REGEX("\\b[a-zA-Z_][a-zA-Z0-9_]{" + (min_length-1) + ",}\\b")
    RETURN REGEX_FIND_ALL(text, pattern)
```

## Token Priority (Expansion Order)

```
IMPORTANT: Tokens must be replaced in this order during expansion:

1. Local tokens (~0, ~1, ~2, ...)     - shortest prefix
2. Type tokens  (~*0, ~*1, ~*2, ...)  - medium prefix  
3. Global tokens (~^0, ~^1, ~^2, ...) - longest prefix
4. Escaped tildes (~~ → ~)            - last step

This prevents ~0 from matching inside ~^0 or ~*0.
```
