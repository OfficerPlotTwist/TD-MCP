import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from webserver_callbacks import sanitize_name, unique_name

assert sanitize_name('Third Eye!') == 'Third_Eye'
assert sanitize_name('  hat  ') == 'hat'
assert sanitize_name('9lives') == 'Mask_9lives'
assert sanitize_name('___') == ''
assert sanitize_name('') == ''
assert sanitize_name('a' * 100) == 'a' * 64
assert unique_name('hat', {'in1'}) == 'hat'
assert unique_name('hat', {'hat'}) == 'hat_2'
assert unique_name('hat', {'hat', 'hat_2'}) == 'hat_3'
print('task3 ok')
