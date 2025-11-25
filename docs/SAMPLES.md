# RTO Sample Outputs - What the AI Sees

## Example 1: Python Script

### Original (input.py)
```python
def calculate_total(items, tax_rate=0.08):
    """Calculate the total price including tax."""
    subtotal = sum(item.price for item in items)
    tax = subtotal * tax_rate
    return subtotal + tax

class ShoppingCart:
    def __init__(self):
        self.items = []
    
    def add_item(self, item):
        self.items.append(item)
    
    def get_total(self):
        return calculate_total(self.items)
```

### Compressed (input.rto)
```
{"v":"1.2","m":{"~0":"calculate_total","~1":"items","~2":"subtotal","~3":"tax_rate","~4":"item","~5":"price","~6":"ShoppingCart","~7":"add_item","~8":"get_total"},"ext":"py"}
~*1 ~0(~1, ~3=0.08):
    """Calculate the total ~5 including tax."""
    ~2 = sum(~4.~5 ~*20 ~4 ~*17 ~1)
    tax = ~2 * ~3
    ~*12 ~2 + tax

~*10 ~6:
    ~*1 __init__(~*0):
        ~*0.~1 = []
    
    ~*1 ~7(~*0, ~4):
        ~*0.~1.~^5(~4)
    
    ~*1 ~8(~*0):
        ~*12 ~0(~*0.~1)
```

### Token Legend for this file:
```
LOCAL (~N):
  ~0  → calculate_total
  ~1  → items
  ~2  → subtotal
  ~3  → tax_rate
  ~4  → item
  ~5  → price
  ~6  → ShoppingCart
  ~7  → add_item
  ~8  → get_total

TYPE-SPECIFIC (~*N) for Python:
  ~*0  → self
  ~*1  → def
  ~*10 → class
  ~*12 → return
  ~*17 → in
  ~*20 → for

GLOBAL (~^N):
  ~^5  → append
```

---

## Example 2: JavaScript Function

### Original (utils.js)
```javascript
function fetchUserData(userId) {
    return fetch(`/api/users/${userId}`)
        .then(response => response.json())
        .then(data => {
            console.log('User data:', data);
            return data;
        })
        .catch(error => {
            console.error('Failed to fetch:', error);
            throw error;
        });
}

export default fetchUserData;
```

### Compressed (utils.rto)
```
{"v":"1.2","m":{"~0":"fetchUserData","~1":"userId","~2":"response","~3":"data","~4":"error","~5":"console"},"ext":"js"}
~^0 ~0(~1) {
    ~^1 fetch(`/api/users/${~1}`)
        .then(~2 => ~2.json())
        .then(~3 => {
            ~5.log('User ~3:', ~3);
            ~^1 ~3;
        })
        .~^18(~4 => {
            ~5.~4('Failed to fetch:', ~4);
            ~^22 ~4;
        });
}

~^4 ~^3 ~0;
```

### Token Legend:
```
LOCAL (~N):
  ~0 → fetchUserData
  ~1 → userId
  ~2 → response
  ~3 → data
  ~4 → error
  ~5 → console

GLOBAL (~^N):
  ~^0  → function
  ~^1  → return
  ~^3  → default
  ~^4  → export
  ~^18 → catch
  ~^22 → throw
```

---

## Example 3: C Header File

### Original (utils.h)
```c
#ifndef UTILS_H
#define UTILS_H

#include <stdio.h>
#include <stdlib.h>

typedef struct {
    int width;
    int height;
    unsigned char *data;
} Image;

Image* create_image(int width, int height);
void destroy_image(Image *img);
int process_image(Image *img, float threshold);

#endif
```

### Compressed (utils.rto)
```
{"v":"1.2","m":{"~0":"width","~1":"height","~2":"Image","~3":"image","~4":"threshold"},"ext":"c"}
#~^35 UTILS_H
#~^16 UTILS_H

#~^15 <stdio.h>
#~^15 <stdlib.h>

~^20 ~^17 {
    ~^0 ~0;
    ~^0 ~1;
    ~^32 ~^1 *~^56;
} ~2;

~2* create_~3(~^0 ~0, ~^0 ~1);
~^11 destroy_~3(~2 *img);
~^0 process_~3(~2 *img, ~^2 ~4);

#~^37
```

### Token Legend:
```
LOCAL (~N):
  ~0 → width
  ~1 → height
  ~2 → Image
  ~3 → image
  ~4 → threshold

GLOBAL (~^N):
  ~^0  → int
  ~^1  → char
  ~^2  → float
  ~^11 → void
  ~^15 → include
  ~^16 → define
  ~^17 → struct
  ~^20 → typedef
  ~^32 → unsigned
  ~^35 → ifndef
  ~^37 → endif
  ~^56 → data
```

---

## Example 4: Rust Function

### Original (lib.rs)
```rust
use std::collections::HashMap;

pub fn process_data(items: Vec<String>) -> HashMap<String, usize> {
    let mut result: HashMap<String, usize> = HashMap::new();
    
    for item in items.iter() {
        let count = result.entry(item.clone()).or_insert(0);
        *count += 1;
    }
    
    result
}
```

### Compressed (lib.rto)
```
{"v":"1.2","m":{"~0":"items","~1":"result","~2":"count"},"ext":"rs"}
~*20 std::collections::~*38;

~*18 ~*4 process_data(~0: ~*40<~*41>) -> ~*38<~*41, ~*65> {
    ~*1 ~*2 ~1: ~*38<~*41, ~*65> = ~*38::new();
    
    ~*6 item ~*17 ~0.~*26() {
        ~*1 ~2 = ~1.entry(item.~*24()).or_insert(0);
        *~2 += 1;
    }
    
    ~1
}
```

### Token Legend:
```
LOCAL (~N):
  ~0 → items
  ~1 → result
  ~2 → count

TYPE-SPECIFIC (~*N) for Rust:
  ~*1  → let
  ~*2  → mut
  ~*4  → fn
  ~*6  → for
  ~*17 → in
  ~*18 → pub
  ~*20 → use
  ~*24 → clone
  ~*26 → iter
  ~*38 → HashMap
  ~*40 → Vec
  ~*41 → String
  ~*65 → usize
```

---

## Example 5: Shell Script

### Original (deploy.sh)
```bash
#!/bin/bash
set -e

echo "Starting deployment..."

for file in *.tar.gz; do
    if [ -f "$file" ]; then
        echo "Extracting $file"
        tar -xzf "$file"
    fi
done

echo "Deployment complete!"
```

### Compressed (deploy.rto)
```
{"v":"1.2","m":{"~0":"file","~1":"Deployment","~2":"Extracting"},"ext":"sh"}
#!/bin/bash
~*29 -e

~*31 "Starting ~1..."

~*4 ~0 ~*5 *.tar.gz; ~*8
    ~*0 [ -f "$~0" ]; ~*1
        ~*31 "~2 $~0"
        ~*87 -xzf "$~0"
    ~*3
~*9

~*31 "~1 complete!"
```

### Token Legend:
```
LOCAL (~N):
  ~0 → file
  ~1 → Deployment
  ~2 → Extracting

TYPE-SPECIFIC (~*N) for Shell:
  ~*0  → if
  ~*1  → then
  ~*3  → fi
  ~*4  → for
  ~*5  → in
  ~*8  → do
  ~*9  → done
  ~*29 → set
  ~*31 → echo
  ~*87 → tar
```

---

## How LLMs Expand This

When an LLM receives compressed text, it can expand it by:

1. **Parse JSON header** → Extract local dictionary `"m":{...}`
2. **Apply local dict** → Replace `~0`, `~1`, etc. with words from header
3. **Apply type dict** → Replace `~*N` with language keywords (built-in knowledge)
4. **Apply global dict** → Replace `~^N` with common keywords (built-in knowledge)
5. **Unescape tildes** → Replace `~~` with literal `~`

### LLM Prompt Example:
```
This is RTO-compressed Python code. The header contains the local dictionary.
Tokens: ~N=local (from header), ~*N=Python keywords, ~^N=global keywords.

Please expand and explain this code:

{"v":"1.2","m":{"~0":"calculate_total","~1":"items"},"ext":"py"}
~*1 ~0(~1):
    ~*12 sum(i.price ~*20 i ~*17 ~1)
```

### Expected LLM Response:
```python
def calculate_total(items):
    return sum(i.price for i in items)
```
