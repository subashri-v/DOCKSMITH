import os

greeting = os.environ.get("GREETING", "Hello")
print(f"{greeting} from Docksmith!")
print("Container is running successfully.")

# test change for presentation 1