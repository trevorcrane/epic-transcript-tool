# TEA PARTY 🦄

Kids' game based on Sage Crane's *The Unicorntastic Tea Party and the Purr-fect Surprise*.
Pick a unicorn, choose a horn color and outfit, plan the tea party, then search the woods for the 7 missing kitty-corns before time runs out.

Run it from a web server (images won't load from a double-clicked file):

    cd tea-party-game && python3 -m http.server 8000   # open http://localhost:8000

Art: `assets/unicorns` (cut from the supplied sheet; `h*.png` = horn masks used for recoloring), `assets/kittens`, `assets/woods.jpg`.
Sound is synthesized live with the Web Audio API (no audio files).
