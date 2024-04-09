#!/usr/bin/env python3

from PIL import ImageFont, ImageDraw
from skimage import io
from src.utils import *
import os
import re
from src.download_fonts import download_fonts
import requests
import sys
from poster_generator import generator, get_font_by_lang, fonts


def hex_to_rgb(hex_color):
    hex_color_clean = hex_color.lstrip('#').strip()
    return tuple(
        int(hex_color_clean[i:i + 2], 16) for i in range(0, 6, 2)
    )

def get_channel_value(channel):
    """Helper to calculate luminance."""
    channel = channel / 255.0
    if channel <= 0.03928:
        channel = channel / 12.92
    else:
        channel = ((channel + 0.055) / 1.055) ** 2.4
    return channel

def calculate_color_luminance(rgb_tuple):
    """Get color luminance.

    Used formula from w3c guide:
    https://www.w3.org/TR/WCAG20/#relativeluminancedef

    L = 0.2126 * R + 0.7152 * G + 0.0722 * B where R, G and B are defined as:

    if RsRGB <= 0.03928 then R = RsRGB/12.92 else R = ((RsRGB+0.055)/1.055) ^ 2.4
    if GsRGB <= 0.03928 then G = GsRGB/12.92 else G = ((GsRGB+0.055)/1.055) ^ 2.4
    if BsRGB <= 0.03928 then B = BsRGB/12.92 else B = ((BsRGB+0.055)/1.055) ^ 2.4
    """
    r, g, b = rgb_tuple
    r = get_channel_value(r)
    g = get_channel_value(g)
    b = get_channel_value(b)
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return luminance

def get_foreground(background_color, output='hex'):
    """Get foreground font color based on w3c recommendations."""
    hex_white = '#FFFFFF'
    hex_black = '#000000'
    rgb_white = (255, 255, 255)
    rgb_black = (0, 0, 0)

    # convert to rgb if got hex
    if isinstance(background_color, str):
        background_color =  hex_to_rgb(background_color)

    luminance = calculate_color_luminance(background_color)
    if (luminance + 0.05) / (0.0 + 0.05) > (1.0 + 0.05) / (luminance + 0.05):
        return (rgb_black, 'black') if output.lower() == 'rgb' else (hex_black, 'black')
    else:
        return (rgb_white, 'white') if output.lower() == 'rgb' else (hex_white, 'white')

def card_generator(link_id, options: dict, link_type="albums") -> ImageDraw:

    DPI = 118 # 118
    resolution = (int(54 * 50), int(85.4 * 50)) # roughly 300 DPI - 118.xx
    # scannables.scdn.co maxes out at 2047 px

    data = spotify_data_pull(link_id, link_type)

    # ensure that album data could be fetched
    if data is None:
        return None, None

    spacing = int(resolution[0] * 0.03)
    y_position = 0

    #
    # define color scheme based on theme variable
    #
    theme = options['theme']
    if theme == "light":
        background_color = (255, 255, 255, 255) # white background
        text_color = (0, 0, 0) # black text
    elif theme == "dark":
        background_color = (10, 10, 10, 255) # dark background
        text_color = (255, 255, 255) # white text

    #
    # define poster
    #
    album_art = io.imread(data['album_art'])
    album_art = Image.fromarray(album_art)
    palette = dominant_colors(np.array(album_art))
    background_color = (palette[0][0], palette[0][1], palette[0][2], 255)
    poster = Image.new('RGBA', resolution, color=background_color)
    print(palette[0][0], palette[0][1], palette[0][2])

    #
    # album art
    #
    # album_art = io.imread(data['album_art'])
    # album_art = Image.fromarray(album_art)
    album_art_size = min(resolution[0] - 2 * spacing, int((resolution[1] - 2 * spacing) * 0.6))  # full width but no larger than 60% of height
    album_art = album_art.resize((album_art_size, album_art_size))

    mask = np.zeros(album_art.size, np.uint8)
    mask = rounded_rectangle(mask, (0,0), album_art.size, 0.1, color=(255,255,255), thickness=-1)
    mask = Image.fromarray(mask)

    poster.paste(album_art, (int(0.5 * resolution[0] - 0.5 * album_art_size), spacing), mask)

    y_position += album_art_size + 2 * spacing

    #
    # make the poster drawable
    #
    poster_draw = ImageDraw.Draw(poster, 'RGBA')

    #
    # album artist
    #
    max_text_length = int((resolution[0] - 2 * spacing) * 0.65)  # 65% of width is maximum
    artist_font_size = int(max_text_length / 9)  # constant 9 calculated based on width of 3300 and font size 170
    artist_font = ImageFont.truetype(get_font_by_lang(data['album_artist'][1], "bold"), artist_font_size)

    text_length = artist_font.getlength(data['album_artist'][0])
    if text_length > max_text_length:
        reduce_factor = max_text_length / text_length  # calculate factor to get precise font size if too large
        artist_font = ImageFont.truetype(get_font_by_lang(data['album_artist'][1], "bold"), int(artist_font_size * reduce_factor))

    poster_draw.text((spacing, y_position), data['album_artist'][0],text_color, font=artist_font)

    y_position += artist_font.getbbox(data['album_artist'][0])[3] + spacing

    #
    # album name
    #
    max_text_length = int((resolution[0] - 2 * spacing) * 0.75)  # 75% of width is maximum
    album_font_size = int(max_text_length / 27)  # constant 27 calculated based on width of 3300 and font size 80
    album_font = ImageFont.truetype(get_font_by_lang(data['album_name'][1], "thin"), album_font_size)

    text_length = album_font.getlength(data['album_name'][0])
    if text_length > max_text_length:
        reduce_factor = max_text_length / text_length  # calculate factor to get precise font size if too large
        album_font = ImageFont.truetype(get_font_by_lang(data['album_name'][1], "thin"), int(album_font_size * reduce_factor))

    poster_draw.text((spacing, y_position), data['album_name'][0], text_color, font=album_font)

    #
    # playtime
    #
    playtime_font_size = int(album_font_size//1.5)
    playtime_font = ImageFont.truetype(fonts['source-code-pro.light.ttf'], playtime_font_size)
    playtime_y_position = y_position + int(artist_font.size/2.25) - playtime_font.size  # align playtime with bottom of album name instead of top
    poster_draw.text((resolution[0] - spacing - playtime_font.getbbox(data['playtime'])[2], playtime_y_position), data['playtime'], text_color, font=playtime_font)

    y_position += 2*spacing

    #
    # color palette
    #
    # palette = dominant_colors(np.array(album_art))

    x_posn = spacing
    line_height = resolution[1] * 0.01
    for color in palette:
        poster_draw.rectangle([x_posn, y_position, x_posn+(resolution[0] - 2*spacing)/len(palette), y_position+line_height], fill=tuple(color), width=50)
        x_posn += (resolution[0] - 2*spacing)/len(palette)

    y_position += spacing

    #
    # tracks
    #
    track_font_size = album_font_size
    track_font = ImageFont.truetype(fonts['NotoSansJP-Thin.ttf'], track_font_size)
    track_line = ""
    for track in data['tracks']:
        if options['remove_featured_artists']:
            # remove anything inside parentheses including the parentheses
            track = re.sub(r'\([^)]*\)', '', track)
            track = re.sub(r'\[[^)]*\]', '', track)
            track = track.strip()

        if track_font.getlength(track_line) < resolution[0] - spacing:
            track_line = track_line + track + " | "

        if track_font.getlength(track_line) >= resolution[0] - spacing:
            track_line = track_line[:len(track_line) - len(track + " | ")]
            poster_draw.text((spacing, y_position), track_line, text_color, font=track_font)
            track_line = track + " | "
            y_position += track_font.getbbox(track_line)[3]

    poster_draw.text((spacing, y_position), track_line, text_color, font=track_font)

    #
    # spotify scan code
    #
    # code_size = max(round(resolution[1] / 5), 256)  # absolute width of requested spotify code
    code_size = max(2047, 256)  # absolute width of requested spotify code
    if theme == 'light':
        spotify_code_url = f'https://scannables.scdn.co/uri/plain/jpeg/FFFFFF/black/{code_size}/spotify:album:{data["album_id"]}'
    elif theme == 'dark':
        spotify_code_url = f'https://scannables.scdn.co/uri/plain/jpeg/101010/white/{code_size}/spotify:album:{data["album_id"]}'
    spotify_code = image_from_url(spotify_code_url)
    print(spotify_code.size)

    if spotify_code is not None:
        # spotify_code.resize((resolution[0] - spacing, resolution[0] -  spacing))
        spotify_code = spotify_code.resize((int(resolution[0]*0.75), int(((resolution[0]/spotify_code.size[0])*spotify_code.size[1])*0.75)))
        # spotify_code.resize((int((resolution[0] - 1 * spacing) * code_scale), int((resolution[0] - 1 * spacing) * code_scale / 1)))
        code_width, code_height = spotify_code.size
        print(spotify_code.size)
        # code_position = (spacing, resolution[1] - int(spacing/1) - int(1.3*code_height))
        code_position = ( int(( resolution[0] / 2 ) - ( code_width / 2 )), resolution[1] - int(spacing/1) - int(1.3*code_height))
        if theme == 'dark':
            spotify_code_array = np.array(spotify_code)
            spotify_code_array[spotify_code_array == 16] = 10
            spotify_code = Image.fromarray(spotify_code_array)
        poster.paste(spotify_code, code_position)

    #
    # record label and release date
    #
    label_font_size = playtime_font_size
    label_font = ImageFont.truetype(get_font_by_lang(data['record'][1], "thin"), label_font_size)
    label_offset = label_font.getbbox(data['release_date'])[3]  # offset to set label text over date text
    poster_draw.text((spacing, resolution[1] - 1.5*spacing - label_offset), data['record'][0], text_color, label_font)

    poster_draw.text((spacing, resolution[1] - 1.5*spacing), data['release_date'], text_color, label_font)

    # return final poster and filename friendly album name (no special characters)
    invalid_chars = r"#%&{}\\<>*?\ $!'\":@+`|="
    pattern = "[" + re.escape(invalid_chars) + "]"
    filename_friendly_album_name = re.sub(pattern, "_", data['album_name'][0])
    
    return poster, filename_friendly_album_name


def generate_save_cards(link_id, options: dict, link_type="albums"):

    DPI = 50 # 118
    resolution = (int(54 * 50), int(85.4 * 50)) # roughly 300 DPI - 118.xx
    # scannables.scdn.co maxes out at 2047 px

    data = spotify_data_pull(link_id, link_type)

    # ensure that album data could be fetched
    if data is None:
        return

    spacing = int(resolution[0] * 0.03) # 0.03

    #
    # album art
    #
    album_art = io.imread(data['album_art'])
    album_art = Image.fromarray(album_art)
    album_art_size = min(resolution[0] - 2 * (1.5*spacing), int((resolution[1] - 2 * (1.5*spacing)) * 0.6))  # full width but no larger than 60% of height
    album_art = album_art.resize((album_art_size, album_art_size))

    palette = dominant_colors(np.array(album_art))

    background_colors = [
        [255, 255, 255],
        # [0, 0, 0],
        [10, 10, 10],
    ] + palette[:5]

    # for testing
    # background_colors = [background_colors[2]]

    for idx, background_color in enumerate(reversed(background_colors)):
        text_color, fg_color = get_foreground(background_color, output='RGB')
        # text_hex = "{:02x}{:02x}{:02x}".format(*text_color)
        background_hex = "{:02x}{:02x}{:02x}".format(*background_color)

        #
        # define poster
        #
        bg_color = (background_color[0], background_color[1], background_color[2], 255)
        poster = Image.new('RGBA', resolution, color=bg_color)

        mask = np.zeros(album_art.size, np.uint8)
        mask = rounded_rectangle(mask, (0,0), album_art.size, 0.08, color=(255,255,255), thickness=-1) # 0.1
        mask = Image.fromarray(mask)

        poster.paste(album_art, (int(0.5 * resolution[0] - 0.5 * album_art_size), int(1.5*spacing)), mask)
    
        y_position = album_art_size + 2 * spacing

        #
        # make the poster drawable
        #
        poster_draw = ImageDraw.Draw(poster, 'RGBA')

        #
        # album artist
        #
        max_text_length = int((resolution[0] - 2 * spacing) * 0.65)  # 65% of width is maximum
        artist_font_size = int(max_text_length / 9)  # constant 9 calculated based on width of 3300 and font size 170
        artist_font = ImageFont.truetype(get_font_by_lang(data['album_artist'][1], "bold"), artist_font_size)

        text_length = artist_font.getlength(data['album_artist'][0])
        if text_length > max_text_length:
            reduce_factor = max_text_length / text_length  # calculate factor to get precise font size if too large
            artist_font = ImageFont.truetype(get_font_by_lang(data['album_artist'][1], "bold"), int(artist_font_size * reduce_factor))

        poster_draw.text((spacing, y_position), data['album_artist'][0], text_color, font=artist_font)

        # y_position += artist_font.getbbox(data['album_artist'][0])[3] + spacing
        y_position += artist_font.getbbox('A')[3] + spacing

        #
        # album name
        #
        max_text_length = int((resolution[0] - 2 * spacing) * 0.75)  # 75% of width is maximum
        album_font_size = int(max_text_length / 27)  # constant 27 calculated based on width of 3300 and font size 80
        album_font = ImageFont.truetype(get_font_by_lang(data['album_name'][1], "thin"), album_font_size)

        text_length = album_font.getlength(data['album_name'][0])
        if text_length > max_text_length:
            reduce_factor = max_text_length / text_length  # calculate factor to get precise font size if too large
            album_font = ImageFont.truetype(get_font_by_lang(data['album_name'][1], "thin"), int(album_font_size * reduce_factor))

        poster_draw.text((spacing, y_position), data['album_name'][0], text_color, font=album_font)

        #
        # playtime
        #
        playtime_font_size = int(album_font_size//1.5)
        playtime_font = ImageFont.truetype(fonts['source-code-pro.light.ttf'], playtime_font_size)
        playtime_y_position = y_position + int(artist_font.size/2.25) - playtime_font.size  # align playtime with bottom of album name instead of top
        poster_draw.text((resolution[0] - spacing - playtime_font.getbbox(data['playtime'])[2], playtime_y_position), data['playtime'], text_color, font=playtime_font)

        y_position += 2*spacing

        #
        # color palette
        #
        # palette = dominant_colors(np.array(album_art))

        x_posn = spacing
        line_height = resolution[1] * 0.01
        for color in palette:
            poster_draw.rectangle([x_posn, y_position, x_posn+(resolution[0] - 2*spacing)/len(palette), y_position+line_height], fill=tuple(color), width=50)
            x_posn += (resolution[0] - 2*spacing)/len(palette)

        y_position += spacing

        #
        # tracks
        #
        track_font_size = album_font_size
        track_font = ImageFont.truetype(fonts['NotoSansJP-Thin.ttf'], track_font_size)
        track_line = ""
        lines = 0
        for track in data['tracks']:
            if options['remove_featured_artists']:
                # remove anything inside parentheses including the parentheses
                track = re.sub(r'\([^)]*\)', '', track)
                track = re.sub(r'\[[^)]*\]', '', track)
                track = track.strip()

            if track_font.getlength(track_line) < resolution[0] - 2 * spacing:
                # track_line = track_line + track + " | "
                track_line = track if len(track_line) == 0 else track_line + " | " + track

            if track_font.getlength(track_line) >= resolution[0] - 2 * spacing:
                # track_line = track_line[:len(track_line) - len(track + " | ")]
                track_line = track_line[:len(track_line) - len(" | " + track)]
                poster_draw.text((spacing, y_position), track_line, text_color, font=track_font)
                lines += 1
                # track_line = track + " | "
                track_line = track
                # y_position += track_font.getbbox(track_line)[3]
                y_position += track_font.getbbox('g')[3]

        if lines < 4:
            poster_draw.text((spacing, y_position), track_line, text_color, font=track_font)

        #
        # spotify scan code
        #
        # code_size = max(round(resolution[1] / 5), 256)  # absolute width of requested spotify code
        code_size = max(2047, 256)  # absolute width of requested spotify code
        spotify_code_url = f'https://scannables.scdn.co/uri/plain/png/{background_hex}/{fg_color}/{code_size}/spotify:album:{data["album_id"]}'
        spotify_code = image_from_url(spotify_code_url)

        if spotify_code is not None:
            spotify_code = spotify_code.resize((int(resolution[0]*0.75), int(((resolution[0]/spotify_code.size[0])*spotify_code.size[1])*0.75)))
            code_width, code_height = spotify_code.size
            code_position = ( int(( resolution[0] / 2 ) - ( code_width / 2 )), resolution[1] - int(spacing/1) - int(1.3*code_height))
            if theme == 'dark':
                spotify_code_array = np.array(spotify_code)
                spotify_code_array[spotify_code_array == 16] = 10
                spotify_code = Image.fromarray(spotify_code_array)
            poster.paste(spotify_code, code_position)

        #
        # record label and release date
        #
        # label_font_size = playtime_font_size
        label_font_size = int(album_font_size//1.3)
        label_font = ImageFont.truetype(get_font_by_lang(data['record'][1], "thin"), label_font_size)
        label_offset = label_font.getbbox(data['release_date'])[3]  # offset to set label text over date text
        poster_draw.text((spacing, resolution[1] - 1.5*spacing - label_offset), data['record'][0], text_color, label_font)
        poster_draw.text((spacing, resolution[1] - 1.5*spacing), data['release_date'], text_color, label_font)

        # return final poster and filename friendly album name (no special characters)
        invalid_chars = r"#%&{}\\<>*?\ $!'\":@+`|="
        pattern = "[" + re.escape(invalid_chars) + "]"
        filename_friendly_album_name = re.sub(pattern, "_", data['album_name'][0])

        print(f"{filename_friendly_album_name}-poster-{idx}.png")
        poster.save(f"{filename_friendly_album_name}-poster-{idx}.png")

if __name__ == '__main__':

    for album in sys.argv[1:]:

        if re.match(r'https://spotify.link/([a-zA-Z0-9]+)', album):
            album = requests.get(album).url

        pattern = r'^(https://open\.spotify\.com/|spotify:)(?P<type>album|track|playlist)[:/](?P<id>[a-zA-Z0-9]+)'

        match = re.match(pattern, album)
        if not match:
            print("Invalid link")
            exit()

        link_id = match.groupdict()['id']
        link_type = match.groupdict()['type']

        resolution = (int(54 * 120), int(85.4 * 120))
        theme = 'dark'
        remove_artist_names = 'no'
        
        options = {'theme': theme, 'remove_featured_artists': remove_artist_names}

        # poster, filename = generator(link_id, resolution, options, link_type)

        # poster.save(f"{filename}_poster.png")

        generate_save_cards(link_id, options, link_type)
