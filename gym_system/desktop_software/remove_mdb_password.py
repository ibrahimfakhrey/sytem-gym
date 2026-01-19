"""
Remove password from .mdb file (Access 97-2003)
This script clears the password bytes in the file header.
"""

import sys
import shutil


def remove_mdb_password(file_path: str, output_path: str = None) -> bool:
    """
    Remove password from .mdb file by clearing the password bytes in header.

    Access 97-2003 stores the password at offset 0x42, XOR'd with a known mask.
    Setting these bytes to the XOR mask values effectively sets an empty password.
    """

    # XOR mask for Access 2000/2003
    xor_mask_2000 = bytes([
        0xC7, 0x89, 0x6F, 0x32, 0xBC, 0x19, 0x9E, 0xEC,
        0x17, 0xFB, 0x33, 0x8E, 0x5D, 0x70, 0xBA, 0xD7,
        0x6E, 0xBB, 0x92, 0x47
    ])

    # XOR mask for Access 97
    xor_mask_97 = bytes([
        0x86, 0xFB, 0xEC, 0x37, 0x5D, 0x44, 0x9C, 0xFA,
        0xC6, 0x5E, 0x28, 0xE6, 0x13
    ])

    try:
        # Read entire file
        with open(file_path, 'rb') as f:
            data = bytearray(f.read())

        # Check Jet version at offset 0x14
        jet_version = data[0x14] if len(data) > 0x14 else 0

        if jet_version == 0:  # Access 97
            xor_mask = xor_mask_97
            pwd_offset = 0x42
            pwd_len = 13
        else:  # Access 2000/2003
            xor_mask = xor_mask_2000
            pwd_offset = 0x42
            pwd_len = 20

        print(f"Detected Jet version: {jet_version} ({'Access 97' if jet_version == 0 else 'Access 2000/2003'})")
        print(f"Password offset: 0x{pwd_offset:02X}, length: {pwd_len}")

        # Show current password bytes
        current_pwd_bytes = data[pwd_offset:pwd_offset + pwd_len]
        print(f"Current password bytes: {current_pwd_bytes.hex()}")

        # Calculate what the password is
        decoded = []
        for i, byte in enumerate(current_pwd_bytes):
            if i < len(xor_mask):
                decoded_byte = byte ^ xor_mask[i]
                decoded.append(decoded_byte)
        print(f"Decoded password bytes: {bytes(decoded).hex()}")

        # Set password bytes to XOR mask (empty password)
        # When XOR'd with the mask, this gives all zeros = no password
        for i in range(pwd_len):
            if i < len(xor_mask):
                data[pwd_offset + i] = xor_mask[i]

        print(f"New password bytes: {data[pwd_offset:pwd_offset + pwd_len].hex()}")

        # Also need to clear the database password flag
        # The flag is at different locations depending on version
        # For Jet 4.0 (Access 2000+), there are additional encryption flags

        # Clear encryption flag at offset 0x62 (98) for some versions
        if len(data) > 0x62:
            data[0x62] = 0x00

        # Clear additional encryption indicator at 0x298
        if len(data) > 0x298:
            data[0x298] = 0x00

        # Write output file
        if output_path is None:
            output_path = file_path

        with open(output_path, 'wb') as f:
            f.write(data)

        print(f"\nPassword removed! Saved to: {output_path}")
        return True

    except Exception as e:
        print(f"Error: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python remove_mdb_password.py <input.mdb> [output.mdb]")
        print("\nIf output is not specified, the input file will be modified in place.")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    # If modifying in place, create backup
    if output_file is None:
        backup_file = input_file + ".backup"
        shutil.copy(input_file, backup_file)
        print(f"Created backup: {backup_file}")

    remove_mdb_password(input_file, output_file)


if __name__ == "__main__":
    main()
