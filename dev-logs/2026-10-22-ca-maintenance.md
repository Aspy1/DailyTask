# Certificate trust maintenance

Updated the project environment to pip 26.2.2 and certifi 2026.10.19. Added the certifi minimum to requirements.txt and regenerated the existing pinned package set without adding local audit tools. The legacy UTF-16 lock was normalized to UTF-8. pip check passed. No application source or user data was changed.
