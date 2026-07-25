import sys
from unittest.mock import MagicMock
sys.modules['pygame'] = MagicMock()
sys.modules['pygame.locals'] = MagicMock()
